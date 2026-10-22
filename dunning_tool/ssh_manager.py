# -*- coding: utf-8 -*-
"""
ssh_manager.py - remote command execution via paramiko.

Implements the jobserver restart sequence used by the original tool:
    1. stop jobserver (verify "jobserver shutdown ok.")
    2. start jobserver
    3. confirm the process is alive ("ps -ef | grep -w 'Dz_app=jobserver'")
with retries and per-command timeouts taken from config.json.

The manager receives both a `log` callable and a `tr` translator so its
messages are localised by the same i18n dictionary the GUI uses.
"""

import time

import paramiko


class SSHError(Exception):
    """Raised when a remote command fails or times out."""


class SSHManager:
    BOSS_DIR = "/job/cvbsjob/r13"
    STOP_OK = "jobserver shutdown ok."
    PROC_PATTERN = "Dz_app=jobserver"

    def __init__(self, ssh_config, log=None, tr=None):
        self._cfg = ssh_config
        self._log = log or (lambda msg: None)
        self._tr = tr or (lambda text, **kw: text)

    def _t(self, key, **kwargs):
        self._log(self._tr(key, **kwargs))

    # ------------------------------------------------------------------
    def _connect(self):
        if self._client is not None:
            return
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self._cfg["host"],
                port=int(self._cfg.get("port", 22)),
                username=self._cfg["username"],
                password=self._cfg["password"],
                timeout=int(self._cfg.get("connect_timeout", 15)),
            )
        except Exception as exc:
            try:
                client.close()
            except Exception:
                pass
            raise SSHError("SSH connect to %s failed: %s"
                           % (self._cfg["host"], exc))
        self._client = client

    _client = None

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    # ------------------------------------------------------------------
    def run(self, command, timeout=None):
        """Execute one command, return (stdout, stderr, exit_status)."""
        timeout = int(timeout or self._cfg.get("command_timeout", 60))
        self._connect()
        self._t("Executing remote command: {cmd}", cmd=command)
        try:
            stdin, stdout, stderr = self._client.exec_command(command,
                                                              get_pty=True)
        except Exception as exc:
            raise SSHError(self._tr(
                "Failed to execute command: {cmd}, error: {error}",
                cmd=command, error=exc))
        start = time.time()
        while not stdout.channel.exit_status_ready():
            if time.time() - start > timeout:
                stdout.channel.close()
                stderr.channel.close()
                raise SSHError(self._tr(
                    "Command timed out after {timeout} seconds.",
                    timeout=timeout))
            time.sleep(0.1)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="ignore")[:5000]
        err = stderr.read().decode("utf-8", errors="ignore")[:5000]
        return out, err, exit_status

    # ------------------------------------------------------------------
    def _is_running(self):
        out, _, _ = self.run(
            "ps -ef | grep -w '%s' | grep -v grep" % self.PROC_PATTERN,
            timeout=10)
        return bool(out.strip())

    def restart_jobserver(self):
        """Stop then start the jobserver; raise SSHError on failure."""
        retries = int(self._cfg.get("retries", 3))

        # --- stop (best effort, mirrors original 2-attempt loop) ---
        for _ in range(2):
            out, err, _ = self.run(
                "cd %s && ./bosstool stop jobserver" % self.BOSS_DIR)
            if self.STOP_OK in out or self.STOP_OK in err:
                self._t("Jobserver stopped successfully.")
                break
            time.sleep(3)

        # --- start with retries ---
        for attempt in range(1, retries + 1):
            if attempt > 1:
                self._t("Retrying to start Jobserver (attempt {attempt})...",
                        attempt=attempt)
                try:
                    self.run("cd %s && ./bosstool stop jobserver" % self.BOSS_DIR)
                except SSHError:
                    pass  # stop is best-effort during retry
                time.sleep(5)
            self.run("cd %s && ./bosstool start jobserver" % self.BOSS_DIR,
                     timeout=30)
            time.sleep(5)
            if self._is_running():
                self._t("Jobserver process started successfully.")
                return
        raise SSHError(self._tr("Failed to start Jobserver after retries."))
