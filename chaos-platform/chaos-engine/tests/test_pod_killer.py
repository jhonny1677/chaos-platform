"""Unit tests for the pod killer module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.kubernetes.pod_selector import select_for_kill, MAX_KILL_PERCENTAGE


def _make_pod(name: str, ready: bool = True) -> MagicMock:
    pod = MagicMock()
    pod.metadata.name = name
    pod.status.phase = "Running"
    cs = MagicMock()
    cs.ready = ready
    cs.restart_count = 0
    pod.status.container_statuses = [cs]
    return pod


class TestSelectForKill:
    def test_kills_at_least_one_pod(self):
        pods = [_make_pod(f"pod-{i}") for i in range(10)]
        selected = select_for_kill(pods, kill_percentage=5.0)
        assert len(selected) >= 1

    def test_respects_blast_radius_ceiling(self):
        pods = [_make_pod(f"pod-{i}") for i in range(10)]
        selected = select_for_kill(pods, kill_percentage=80.0)
        assert len(selected) <= round(10 * MAX_KILL_PERCENTAGE / 100)

    def test_returns_empty_for_empty_input(self):
        assert select_for_kill([], kill_percentage=50.0) == []

    def test_kill_percentage_twenty(self):
        pods = [_make_pod(f"pod-{i}") for i in range(10)]
        selected = select_for_kill(pods, kill_percentage=20.0)
        # 20% of 10 = 2
        assert len(selected) == 2

    def test_does_not_kill_more_than_available(self):
        pods = [_make_pod("only-pod")]
        selected = select_for_kill(pods, kill_percentage=100.0)
        assert len(selected) == 1


class TestPodKillerExecute:
    async def test_returns_empty_result_when_no_pods(self):
        with (
            patch("app.core.kubernetes.pod_selector.k8s") as mock_k8s,
            patch("app.core.chaos.pod_killer.pod_selector.list_running_pods", new=AsyncMock(return_value=[])),
        ):
            from app.core.chaos.pod_killer import execute
            result = await execute(namespace="target-app", experiment_id="test-001")
            assert result.killed_pods == []
            assert result.targeted_pods == []

    async def test_kills_selected_pods(self):
        pods = [_make_pod(f"pod-{i}") for i in range(3)]
        mock_k8s_client = MagicMock()
        mock_k8s_client.delete_namespaced_pod = MagicMock()

        with (
            patch("app.core.chaos.pod_killer.pod_selector.list_running_pods", new=AsyncMock(return_value=pods)),
            patch("app.core.chaos.pod_killer.k8s") as mock_k8s,
            patch("asyncio.to_thread", new=AsyncMock(return_value=None)),
            patch("app.core.chaos.pod_killer._wait_for_recovery", new=AsyncMock(side_effect=lambda **kw: kw["result"])),
        ):
            mock_k8s.core_v1 = mock_k8s_client
            from app.core.chaos.pod_killer import execute
            result = await execute(namespace="target-app", kill_percentage=100.0, experiment_id="test-002")
            assert len(result.targeted_pods) >= 1
