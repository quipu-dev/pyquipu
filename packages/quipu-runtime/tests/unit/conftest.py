import pytest
from pyquipu.test_utils.fixtures import executor, isolated_vault, mock_runtime_bus


# 保持 autouse 生效
@pytest.fixture(autouse=True)
def _auto_mock_runtime_bus(mock_runtime_bus):
    return mock_runtime_bus


def pytest_configure(config):
    config.addinivalue_line("markers", "timeout(seconds): kill test after a certain time")


__all__ = ["executor", "isolated_vault", "mock_runtime_bus"]
