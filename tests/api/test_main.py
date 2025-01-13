import asyncio
import logging
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from temporalio.client import Client
from temporalio.worker import Worker
from testcontainers.mongodb import MongoDbContainer  # type: ignore

from biosim_server.api.main import app
from biosim_server.io.file_service_local import FileServiceLocal
from biosim_server.omex_sim.biosim1.biosim_service_rest import BiosimServiceRest
from biosim_server.verify.workflows.omex_verify_workflow import OmexVerifyWorkflowInput, OmexVerifyWorkflowOutput, \
    OmexVerifyWorkflowStatus


@pytest.mark.asyncio
async def test_root() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        response = await test_client.get("/")
        assert response.status_code == 200
        assert response.json() == {'docs': 'https://biochecknet.biosimulations.org/docs'}


@pytest.mark.asyncio
async def test_get_output_not_found(omex_verify_workflow_input: OmexVerifyWorkflowInput,
                                    omex_verify_workflow_output: OmexVerifyWorkflowOutput) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        # test with non-existent verification_id
        response = await test_client.get(f"/verify-omex/non-existent-id")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_omex_verify_and_get_output(omex_verify_workflow_input: OmexVerifyWorkflowInput,
                                          omex_verify_workflow_output: OmexVerifyWorkflowOutput,
                                          file_service_local: FileServiceLocal, temporal_client: Client,
                                          temporal_verify_worker: Worker,
                                          biosim_service_rest: BiosimServiceRest) -> None:
    root_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    file_path = root_dir / "local_data" / "BIOMD0000000010_tellurium_Negative_feedback_and_ultrasen.omex"
    assert omex_verify_workflow_input.observables is not None
    query_params: dict[str, float | str | list[str]] = {"workflow_id_prefix": "verification-",
                                                        "simulators": [sim.simulator for sim in
                                                                       omex_verify_workflow_input.requested_simulators],
                                                        "include_outputs": str(False).lower(),
                                                        "user_description": omex_verify_workflow_input.user_description,
                                                        "observables": omex_verify_workflow_input.observables,
                                                        "rTol": omex_verify_workflow_input.rTol,
                                                        "aTol": omex_verify_workflow_input.aTol}

    async with (AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client):
        uploaded_filename = "BIOMD0000000010_tellurium_Negative_feedback_and_ultrasen.omex"
        with open(file_path, "rb") as file:
            files = {"uploaded_file": (uploaded_filename, file, "application/zip")}
            response = await test_client.post("/verify_omex", files=files, params=query_params)

        workflow_output = OmexVerifyWorkflowOutput.model_validate(response.json())
        assert response.status_code == 200
        logging.log(level=logging.INFO, msg=f"workflow_output.workflow_id: {workflow_output.workflow_id}")
        workflow_id = workflow_output.workflow_id

        # poll until the workflow is completed
        while True:
            response = await test_client.get(f"/verify-omex/{workflow_id}")
            assert response.status_code == 200 or response.status_code == 404
            if response.status_code == 200:
                workflow_output = OmexVerifyWorkflowOutput.model_validate_json(response.json())
                if (workflow_output.workflow_status == OmexVerifyWorkflowStatus.COMPLETED.value or
                        workflow_output.workflow_status == OmexVerifyWorkflowStatus.FAILED.value):
                    break
            await asyncio.sleep(1)

    expected_workflow_output = omex_verify_workflow_output.model_copy(deep=True)
    # force the timestamp, job_id, and omex_s3_path before comparison (these are set on server)
    expected_workflow_output.workflow_input.source_omex.omex_s3_file = workflow_output.workflow_input.source_omex.omex_s3_file
    expected_workflow_output.workflow_id = workflow_id
    expected_workflow_output.timestamp = workflow_output.timestamp
    expected_workflow_output.workflow_run_id = workflow_output.workflow_run_id
    expected_workflow_output.workflow_status = workflow_output.workflow_status
    assert expected_workflow_output.workflow_input == workflow_output.workflow_input

    assert expected_workflow_output == workflow_output
