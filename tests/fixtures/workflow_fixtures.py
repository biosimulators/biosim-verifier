import os
import uuid
from pathlib import Path

import pytest
from testcontainers.mongodb import MongoDbContainer  # type: ignore

from biosim_server.omex_sim.biosim1.models import SourceOmex, BiosimSimulatorSpec
from biosim_server.verify.workflows.omex_verify_workflow import OmexVerifyWorkflowOutput, OmexVerifyWorkflowInput


@pytest.fixture(scope="function")
def omex_verify_workflow_id() -> str:
    return "verification-" + str(uuid.uuid4())


@pytest.fixture(scope="function")
def omex_verify_workflow_input() -> OmexVerifyWorkflowInput:
    path = "path/to/omex"
    simulators = [BiosimSimulatorSpec(simulator="copasi"), BiosimSimulatorSpec(simulator="vcell")]
    include_outputs = False
    rTol = 1e-6
    aTol = 1e-9
    observables = ["time", "concentration"]
    omex_input = OmexVerifyWorkflowInput(source_omex=SourceOmex(omex_s3_file=path, name="name"),
        user_description="description", requested_simulators=simulators, include_outputs=include_outputs, rTol=rTol,
        aTol=aTol, observables=observables)
    return omex_input


@pytest.fixture(scope="function")
def omex_verify_workflow_output(omex_verify_workflow_input: OmexVerifyWorkflowInput,
                                omex_verify_workflow_id: str) -> OmexVerifyWorkflowOutput:
    root_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    with open(root_dir / "local_data" / "OmexVerifyWorkflowOutput_expected.json") as f:
        workflow_output = OmexVerifyWorkflowOutput.model_validate_json(f.read())
        workflow_output.workflow_id = omex_verify_workflow_id
        return workflow_output
