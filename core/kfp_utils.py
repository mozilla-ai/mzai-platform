# core/kfp_utils.py

import json
import logging
import requests

from django.conf import settings
from kfp import client as kfp_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)

def find_artifact_uri(
    run_id: str,
    step_name: str,
    artifact_name: str,
    kfp_host: str = None,
) -> str | None:
    """
    Fetches a usable HTTP URL for a run's artifact by parsing the Argo
    workflow manifest (via KFP SDK or REST API) and translating MinIO URIs
    into the KFP UI's artifact gateway.

    Returns an HTTP(s) URL you can directly GET.
    """
    # allow override or fallback to settings
    if not kfp_host:
        kfp_host = settings.KFP_API_URL.rstrip('/')
    else:
        kfp_host = kfp_host.rstrip('/')

    manifest_str = None
    # 1) Try using the Python SDK
    try:
        client = kfp_client.Client(host=kfp_host)
        run_obj = client.get_run(run_id=run_id)

        pr = getattr(run_obj, 'pipeline_runtime', None)
        if pr and hasattr(pr, 'workflow_manifest'):
            manifest_str = pr.workflow_manifest
        elif hasattr(run_obj, 'run_details'):
            rd = run_obj.run_details
            pr2 = getattr(rd, 'pipeline_runtime', None)
            if pr2 and hasattr(pr2, 'workflow_manifest'):
                manifest_str = pr2.workflow_manifest
    except Exception as e:
        logger.error("SDK get_run failed: %s", e)

    # 2) Fallback to direct REST call
    if not manifest_str:
        try:
            url = f"{kfp_host}/apis/v1beta1/runs/{run_id}"
            headers = {}
            token = getattr(settings, 'KFP_AUTH_TOKEN', None)
            if token:
                headers['Authorization'] = f"Bearer {token}"
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            pr = data.get('pipeline_runtime', {})
            manifest_str = pr.get('workflow_manifest')
            if not manifest_str:
                pr2 = data.get('run', {}).get('pipeline_runtime', {})
                manifest_str = pr2.get('workflow_manifest')
        except Exception as e:
            logger.error("REST fetch manifest failed: %s", e)

    if not manifest_str:
        logger.error("No workflow manifest for run %s", run_id)
        return None

    # parse manifest
    try:
        wf = json.loads(manifest_str)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON manifest for run %s: %s", run_id, e)
        return None

    # locate artifact URI
    raw_uri = None
    for node in wf.get("status", {}).get("nodes", {}).values():
        if node.get("displayName") != step_name:
            continue
        params = node.get("inputs", {}).get("parameters", [])
        patch = next((p for p in params if p.get("name") == "pod-spec-patch"), None)
        if not patch or not patch.get("value"):
            continue
        try:
            pod_spec = json.loads(patch["value"])
            cmd = pod_spec.get("containers", [])[0].get("command", [])
            idx = cmd.index("--executor_input") + 1
            exec_in = json.loads(cmd[idx])
            arts = (
                exec_in
                .get("outputs", {})
                .get("artifacts", {})
                .get(artifact_name, {})
                .get("artifacts", [])
            )
            if arts:
                raw_uri = arts[0].get("uri")
                break
        except Exception as e:
            logger.error("Extract executor_input error: %s", e)
            continue

    if not raw_uri:
        logger.error("Artifact '%s' not found in run %s", artifact_name, run_id)
        return None

    # translate minio:// into HTTP via KFP UI
    if raw_uri.startswith("minio://"):
        # strip scheme
        path = raw_uri.split("minio://", 1)[1]
        ui_base = settings.KFP_UI_URL.rstrip('/')
        return f"{ui_base}/artifacts/minio/{path}"

    # otherwise return as-is
    return raw_uri
