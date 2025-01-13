import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
from _pytest.config.argparsing import Parser

from tests.fixtures.biosim_fixtures import (  # noqa: F401
    biosim_service_mock,
    biosim_service_rest
)
from tests.fixtures.database_fixtures import (  # noqa: F401
    mongodb_container,
    mongo_test_client,
    mongo_test_database,
    mongo_test_collection,
)
from tests.fixtures.s3_fixtures import (  # noqa: F401
    file_service_s3,
    file_service_local
)
from tests.fixtures.temporal_fixtures import (  # noqa: F401
    temporal_env,
    temporal_client,
    temporal_verify_worker
)
from tests.fixtures.workflow_fixtures import (  # noqa: F401
    omex_verify_workflow_id,
    omex_verify_workflow_input,
    omex_verify_workflow_output,
)


# Add the --workflow-environment option
def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--workflow-environment",
        action="store",
        default="local",
        help="Specify the workflow environment"
    )

# If you need to redefine or extend any fixtures, you can do so here.
