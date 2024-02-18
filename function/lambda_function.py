# ---
import boto3, botocore.exceptions
import hashlib
import hmac
import json
import os
import urllib3
from datetime import datetime, timezone, timedelta


def lambda_handler(event, context):
    """Main Lambda invocation function."""
    print(event["headers"])
    print(event["body"])
    # --- Check to see if the signature header has been passed.
    try:
        signature = event["headers"]["X-Hcp-Webhook-Signature"]
    except KeyError:
        return {"statusCode": 403, "body": "HMAC signature not provided."}

    # --- Verify the HMAC, then check the event_action value to determine what to do.
    if verify_hmac(event):
        body = json.loads(event["body"])

        match body["event_action"]:
            case "test":
                return verify()
            case "complete":
                return complete(body)
            case "revoke":
                return revoke(body)
            case "restore":
                return restore(body)
            case "delete":
                return delete(body)
            case _:
                return {
                    "statusCode": 400,
                    "body": f"Action {body['event_action']} found in request is not supported.",
                }
    else:
        return {"statusCode": 403, "body": "Unauthorized: HMAC signature mismatch."}


# --- Event Action functions
def verify():
    """Handle the HCP Packer webhook verification event."""
    response = {"statusCode": "200", "body": "Verification successful!"}
    return response


def complete(body):
    """Handle the HCP Packer 'Completed version' webhook event. Adds metadata tags to the AMI(s)."""
    result = {"actions": []}
    try:
        amis = return_artifact_id(body["event_payload"]["builds"], "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in artifact version."}

        for ami in amis:
            ec2_client = boto3.client("ec2", region_name=ami["region"])
            result_status = "Success"
            result_message = "AMI tags added"
            ami_id = ami["id"]

            # Create a tag for the AMI with the HCP Packer metadata
            try:
                ec2_client.create_tags(
                    Resources=[ami_id],
                    Tags=[
                        {
                            "Key": "HCPPackerBucket",
                            "Value": body["event_payload"]["bucket"]["name"],
                        },
                        {
                            "Key": "HCPPackerVersionFingerprint",
                            "Value": body["event_payload"]["version"]["fingerprint"],
                        },
                        {
                            "Key": "HCPPackerVersion",
                            "Value": body["event_payload"]["version"]["name"],
                        },
                        {
                            "Key": "HCPPackerBuildID",
                            "Value": ami["build_id"],
                        },
                    ],
                )

            except botocore.exceptions.ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code.startswith("InvalidAMIID"):
                    result_status = "Skipped"
                    result_message = error_code
                else:
                    raise e

            result["actions"].append(
                {
                    "ami_id": ami_id,
                    "region": ami["region"],
                    "status": result_status,
                    "message": result_message,
                }
            )

        return {"statusCode": 200, "body": json.dumps(result)}

    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def revoke(body):
    """Handle the HCP Packer 'Revoked version' webhook event. Sets the AMI deprecation time and adds metadata tags."""
    # Set the deprecation time to the current time plus 1 minute (EnableImageDeprecation won't accept a time in the past)
    deprecation_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = {"actions": []}

    try:
        amis = return_artifact_id(body["event_payload"]["builds"], "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in artifact version."}

        for ami in amis:
            ec2_client = boto3.client("ec2", region_name=ami["region"])
            result_status = "Success"
            result_message = f"AMI deprecation time set to {deprecation_time}"
            ami_id = ami["id"]

            try:
                # Enable deprecation for the AMI
                ec2_client.enable_image_deprecation(
                    ImageId=ami_id, DeprecateAt=deprecation_time, DryRun=False
                )

                # Create a tag for the AMI with the deprecation time
                ec2_client.create_tags(
                    Resources=[ami_id],
                    Tags=[
                        {
                            "Key": "HCPPackerRevoked",
                            "Value": "true",
                        },
                        {
                            "Key": "HCPPackerRevokedBy",
                            "Value": body["event_payload"]["version"][
                                "revocation_author"
                            ],
                        },
                        {
                            "Key": "HCPPackerRevocationMessage",
                            "Value": body["event_payload"]["version"][
                                "revocation_message"
                            ],
                        },
                    ],
                )

            except botocore.exceptions.ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code.startswith("InvalidAMIID"):
                    result_status = "Skipped"
                    result_message = error_code
                else:
                    raise e

            result["actions"].append(
                {
                    "ami_id": ami_id,
                    "region": ami["region"],
                    "status": result_status,
                    "message": result_message,
                }
            )

        return {"statusCode": 200, "body": json.dumps(result)}

    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def delete(body):
    """Handle the HCP Packer 'Deleted version' webhook event. Deregisters the AMI(s) and deletes their associated snapshots."""
    result = {"actions": []}
    try:
        amis = return_artifact_id(body["event_payload"]["builds"], "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in artifact version."}

        for ami in amis:
            ec2_client = boto3.client("ec2", region_name=ami["region"])
            result_status = "Success"
            result_message = "AMI deregistered"
            ami_id = ami["id"]

            # Deregister the AMI
            try:
                ec2_client.deregister_image(ImageId=ami_id)
            except botocore.exceptions.ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code.startswith("InvalidAMIID"):
                    result_status = "Skipped"
                    result_message = error_code
                else:
                    raise e

            result["actions"].append(
                {
                    "ami_id": ami_id,
                    "region": ami["region"],
                    "status": result_status,
                    "message": result_message,
                }
            )

            # Get the snapshots associated with the AMI
            snapshots = ec2_client.describe_snapshots(
                Filters=[{"Name": "description", "Values": [f"*{ami_id}*"]}]
            )["Snapshots"]

            # Delete the associated snapshots
            for snapshot in snapshots:
                ec2_client.delete_snapshot(SnapshotId=snapshot["SnapshotId"])
                result["actions"].append(
                    {
                        "snapshot_id": snapshot["SnapshotId"],
                        "region": ami["region"],
                        "status": "Success",
                        "message": f"Snapshot for AMI {ami_id} deleted",
                    }
                )

        return {"statusCode": 200, "body": json.dumps(result)}

    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def restore(body):
    """Handle the HCP Packer 'Restored version' webhook event. Disables deprecation on the AMI and removes the tag added by the 'revoke' handler."""
    result = {"actions": []}
    try:
        # The restore webhook doesn't include the builds object, so we need to call get_builds to get them
        amis = return_artifact_id(body["event_payload"]["builds"], "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in artifact version."}

        for ami in amis:
            ec2_client = boto3.client("ec2", region_name=ami["region"])
            result_status = "Success"
            result_message = "AMI deprecation cleared"
            ami_id = ami["id"]

            try:
                # Disable deprecation for the AMI
                ec2_client.disable_image_deprecation(ImageId=ami_id, DryRun=False)

                # Delete the DeprecationTime tag
                ec2_client.delete_tags(
                    DryRun=False,
                    Resources=[ami_id],
                    Tags=[
                        {"Key": "HCPPackerRevoked"},
                        {"Key": "HCPPackerRevokedBy"},
                        {"Key": "HCPPackerRevocationMessage"},
                    ],
                )

            except botocore.exceptions.ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code.startswith("InvalidAMIID"):
                    result_status = "Skipped"
                    result_message = error_code
                else:
                    raise e

            result["actions"].append(
                {
                    "ami_id": ami_id,
                    "region": ami["region"],
                    "status": result_status,
                    "message": result_message,
                }
            )

        return {"statusCode": 200, "body": json.dumps(result)}

    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


# --- Helper functions
def verify_hmac(event):
    """Verify the HMAC token provided in the event."""
    signature = event["headers"]["X-Hcp-Webhook-Signature"]
    secret = bytes(get_secrets(os.environ.get("HMAC_TOKEN_ARN")), "utf-8")
    message = bytes(event["body"], "utf-8")
    hash = hmac.new(secret, message, hashlib.sha512)
    compare_digest = hmac.compare_digest(hash.hexdigest(), signature)
    return compare_digest


def get_secrets(secret_arn):
    """Get a secret from AWS Secrets Manager. Value is returned as a string."""
    client = boto3.client("secretsmanager")
    token = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    return token


def return_artifact_id(builds, provider):
    """Extracts the artifact IDs for the given cloud provider."""
    artifact_ids = []
    for build in builds:
        if build["platform"] == provider:
            for artifacts in build["artifacts"]:
                artifact_ids.append(
                    {
                        "id": artifacts["external_identifier"],
                        "region": artifacts["region"],
                        "build_id": build["id"],
                    }
                )

    return artifact_ids
