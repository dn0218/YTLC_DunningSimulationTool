# -*- coding: utf-8 -*-
"""
api_manager.py - HTTP job triggering via requests.

Endpoint: POST {base_url}/jobservermgr/api/triggerJob
          ?jobName=<name>&jobGroup=Collection&params=<params>

Receives `log` and `tr` callables so messages are localised.
"""

import time

import requests


class APIError(Exception):
    """Raised when the trigger API cannot be reached or returns an error."""


class APIManager:
    PATH = "/jobservermgr/api/triggerJob"

    # jobservermgr groups seen in the wild:
    #   Collection  - dunning DebitAction jobs (default)
    #   _jobserver_ - platform sync jobs (SKG blacklist sync)
    DEFAULT_GROUP = "Collection"
    SKG_JOBSERVER_GROUP = "_jobserver_"
    SKG_BLACKLIST_SYNC_JOB = "SKGBlacklistSyncJob"

    def __init__(self, api_config, log=None, tr=None):
        self._cfg = api_config
        self._log = log or (lambda msg: None)
        self._tr = tr or (lambda text, **kw: text)

    def _t(self, key, **kwargs):
        self._log(self._tr(key, **kwargs))

    # ------------------------------------------------------------------
    def _build_url(self, job_name, params, job_group):
        base = str(self._cfg["base_url"]).rstrip("/")
        return "%s%s?jobName=%s&jobGroup=%s&params=%s" % (
            base, self.PATH, job_name, job_group, params)

    def _post_with_retry(self, url):
        """POST once per configured retry; returns the last response."""
        timeout = int(self._cfg.get("timeout", 30))
        retries = int(self._cfg.get("retries", 3))

        last_exc = None
        for attempt in range(1, retries + 1):
            self._t("Triggering API: {url}", url=url)
            try:
                resp = requests.post(url, timeout=timeout)
                self._t("API response status: {code}, body: {body}",
                        code=resp.status_code, body=resp.text)
                resp.raise_for_status()
                return resp
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(2)
        self._t("API call failed: {error}", error=last_exc)
        raise APIError("API call failed after %d attempts: %s"
                       % (retries, last_exc))

    def trigger_job(self, job_name, params):
        """Trigger a job on the default Collection group."""
        return self._post_with_retry(
            self._build_url(job_name, params, self.DEFAULT_GROUP))

    def trigger_skg_blacklist_sync_job(self, qry_date):
        """SKGBlacklistSyncJob on the _jobserver_ group (TAB3).

        qry_date: 'YYYY-MM-DD' string (validated/formatted by the caller).
        Full contract (pipeline-separated params):
            QRY_DATE=<yyyy-mm-dd>|REPROCESS=Y|SP_ID=101
        """
        params = "QRY_DATE=%s|REPROCESS=Y|SP_ID=101" % qry_date
        return self._post_with_retry(self._build_url(
            self.SKG_BLACKLIST_SYNC_JOB, params, self.SKG_JOBSERVER_GROUP))

    # ------------------------------------------------------------------
    def trigger_debit_action_job(self):
        """DebitActionJob - generates overdue instances / rule actions."""
        return self.trigger_job("DebitActionJob", "DEBIT_GROUP_TYPE=B|SP_ID=101")

    def trigger_debit_action_deal_job(self):
        """DebitActionDealJob - executes pending debit actions."""
        return self.trigger_job("DebitActionDealJob", "DEBIT_ACTION_DEAL,SP_ID=101")
