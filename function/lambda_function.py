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

    # --- Verify the HMAC, then check the eventAction value to determine what to do.
    if verify_hmac(event):
        body = json.loads(event["body"])

        match body["eventAction"]:
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
                    "body": f"Action {body['eventAction']} found in request is not supported.",
                }
    else:
        return {"statusCode": 403, "body": "Unauthorized: HMAC signature mismatch."}


# --- Event Action functions
def verify():
    """Handle the HCP Packer webhook verification event."""
    response = {"statusCode": "200", "body": "Verification successful!"}
    return response


def complete(body):
    """Handle the HCP Packer 'Completed iteration' webhook event. Adds metadata tags to the AMI(s)."""
    result = {"actions": []}
    try:
        amis = return_image_id(body["eventPayload"]["builds"], "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in iteration."}

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
                            "Value": body["eventPayload"]["bucket"]["slug"],
                        },
                        {
                            "Key": "HCPPackerIterationFingerprint",
                            "Value": body["eventPayload"]["iteration"]["fingerprint"],
                        },
                        {
                            "Key": "HCPPackerIterationVersion",
                            "Value": body["eventPayload"]["iteration"]["version"],
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
    """Handle the HCP Packer 'Revoked iteration' webhook event. Sets the AMI deprecation time and adds metadata tags."""
    # Set the deprecation time to the current time plus 1 minute (EnableImageDeprecation won't accept a time in the past)
    deprecation_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = {"actions": []}

    try:
        # The revoke webhook doesn't include the builds object, so we need to call get_builds to get them
        amis = return_image_id(get_builds(body), "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in iteration."}

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
                            "Value": body["eventPayload"]["iteration"][
                                "revocation_author"
                            ],
                        },
                        {
                            "Key": "HCPPackerRevocationMessage",
                            "Value": body["eventPayload"]["iteration"][
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
    """Handle the HCP Packer 'Deleted iteration' webhook event. Deregisters the AMI(s) and deletes their associated snapshots."""
    result = {"actions": []}
    try:
        amis = return_image_id(body["eventPayload"]["builds"], "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in iteration."}

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
    """Handle the HCP Packer 'Restored iteration' webhook event. Disables deprecation on the AMI and removes the tag added by the 'revoke' handler."""
    result = {"actions": []}
    try:
        # The restore webhook doesn't include the builds object, so we need to call get_builds to get them
        amis = return_image_id(get_builds(body), "aws")
        if len(amis) == 0:
            return {"statusCode": 200, "body": "No AMIs found in iteration."}

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


def get_builds(body):
    """Get the builds associated with an HCP Packer iteration. Used for the webhook events that don't include it in the eventPayload."""
    organization_id = body["eventPayload"]["organization_id"]
    project_id = body["eventPayload"]["project_id"]
    bucket_slug = body["eventPayload"]["bucket"]["slug"]
    iteration_id = body["eventPayload"]["iteration"]["id"]

    access_token = hcp_auth()
    api_url = f"https://api.cloud.hashicorp.com/packer/2021-04-30/organizations/{organization_id}/projects/{project_id}/"
    headers = {"Authorization": f"Bearer {access_token}"}

    http = urllib3.PoolManager()
    response = http.request(
        "GET",
        f"{api_url}/images/{bucket_slug}/iteration?iteration_id={iteration_id}",
        headers=headers,
    )
    if response.status != 200:
        raise Exception(f"Failed to get builds from iteration: {response.data}")
    return json.loads(response.data)["iteration"]["builds"]


def hcp_auth():
    """Get an HCP access token using a service principal key stored in AWS Secrets Manager."""
    credential = json.loads(get_secrets(os.environ.get("HCP_CREDENTIAL_ARN")))
    auth_url = "https://auth.idp.hashicorp.com/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "client_id": credential["HCP_CLIENT_ID"],
        "client_secret": credential["HCP_CLIENT_SECRET"],
        "grant_type": "client_credentials",
        "audience": "https://api.hashicorp.cloud",
    }

    http = urllib3.PoolManager()
    response = http.request_encode_body(
        "POST", auth_url, headers=headers, fields=data, encode_multipart=False
    )
    if response.status != 200:
        raise Exception(f"Failed to get HCP access token: {response.data}")
    return json.loads(response.data)["access_token"]


def return_image_id(builds, provider):
    """Extracts the image IDs for the given cloud provider."""
    image_ids = []
    for build in builds:
        if build["cloud_provider"] == provider:
            for image in build["images"]:
                image_ids.append(
                    {
                        "id": image["image_id"],
                        "region": image["region"],
                        "build_id": build["id"],
                    }
                )

    return image_ids
