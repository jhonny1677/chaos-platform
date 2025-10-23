"""Kubernetes client singleton.

Wraps the official kubernetes-python library (synchronous) and exposes it as
module-level objects. All callers wrap sync K8s calls with asyncio.to_thread()
so they don't block the event loop.

Tries in-cluster config first (running inside a pod); falls back to kubeconfig
for local development.
"""

import logging
from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client import CoreV1Api, AppsV1Api, CustomObjectsApi, BatchV1Api
from kubernetes.config import ConfigException

logger = logging.getLogger("chaos-engine.k8s")

core_v1: CoreV1Api = None
apps_v1: AppsV1Api = None
custom_objects: CustomObjectsApi = None
batch_v1: BatchV1Api = None


def init_kubernetes_client() -> None:
    """Load K8s credentials and initialise API clients.

    Called once at application startup from the lifespan context manager.
    """
    global core_v1, apps_v1, custom_objects, batch_v1

    try:
        k8s_config.load_incluster_config()
        logger.info("Kubernetes: loaded in-cluster config")
    except ConfigException:
        try:
            k8s_config.load_kube_config()
            logger.info("Kubernetes: loaded kubeconfig (local dev mode)")
        except ConfigException as exc:
            logger.error(
                "Kubernetes: no config available — all chaos actions will fail: %s", exc
            )
            return

    core_v1 = CoreV1Api()
    apps_v1 = AppsV1Api()
    custom_objects = CustomObjectsApi()
    batch_v1 = BatchV1Api()
    logger.info("Kubernetes API clients initialised")
