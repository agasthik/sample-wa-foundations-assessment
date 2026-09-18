"""Control Tower Checks (FR-5).

Checks Control Tower deployment status, drift, and version.
Only runs if the current account is the management account.
"""

import boto3


def _get_landing_zone_details(client):
    """Fetch landing zone details, honoring the landing zone's home region.

    ListLandingZones is region-agnostic, but GetLandingZone must be called
    in the landing zone's home region. The home region is embedded in the
    ARN returned by ListLandingZones
    (arn:<partition>:controltower:<home-region>:<account>:landingzone/<id>).

    Returns:
        dict or None: landingZone details, or None if no landing zone exists
    """
    list_resp = client.list_landing_zones()
    landing_zones = list_resp.get("landingZones", [])
    if not landing_zones:
        return None

    lz_arn = landing_zones[0]["arn"]
    home_region = lz_arn.split(":")[3]
    regional_client = boto3.client("controltower", region_name=home_region)
    get_resp = regional_client.get_landing_zone(landingZoneIdentifier=lz_arn)
    return get_resp.get("landingZone", {})


def check_control_tower_deployed():
    """FR-5.1: Verify Control Tower is deployed (landing zone exists)."""
    try:
        client = boto3.client("controltower")
        resp = client.list_landing_zones()
        landing_zones = resp.get("landingZones", [])
        deployed = len(landing_zones) > 0
        return {
            "check": "Control Tower deployed",
            "description": "AWS Control Tower should be deployed for automated multi-account governance.",
            "status": "complete" if deployed else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 6,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/getting-started-with-control-tower.html",
        }
    except Exception as e:
        return {
            "check": "Control Tower deployed",
            "description": "AWS Control Tower should be deployed for automated multi-account governance.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 6,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/getting-started-with-control-tower.html",
            "error": str(e),
        }


def check_control_tower_not_drifted():
    """FR-5.2: Verify Control Tower landing zone is not drifted."""
    try:
        client = boto3.client("controltower")
        landing_zone = _get_landing_zone_details(client)

        if landing_zone is None:
            return {
                "check": "Control Tower not drifted",
                "description": "Control Tower landing zone should not be in a drifted state.",
                "status": "incomplete",
                "required": True,
                "weight": 6,
                "loe": 2,
                "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
            }

        drift_status = landing_zone.get("driftStatus", {}).get("status", "UNKNOWN")
        not_drifted = drift_status != "DRIFTED"

        return {
            "check": "Control Tower not drifted",
            "description": "Control Tower landing zone should not be in a drifted state.",
            "status": "complete" if not_drifted else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
        }
    except Exception as e:
        return {
            "check": "Control Tower not drifted",
            "description": "Control Tower landing zone should not be in a drifted state.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
            "error": str(e),
        }


def check_control_tower_latest_version():
    """FR-5.3: Verify Control Tower is on the latest version."""
    try:
        client = boto3.client("controltower")
        landing_zone = _get_landing_zone_details(client)

        if landing_zone is None:
            return {
                "check": "Control Tower latest version",
                "description": "Control Tower landing zone should be on the latest available version.",
                "status": "incomplete",
                "required": False,
                "weight": 5,
                "loe": 2,
                "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/configuration-updates.html",
            }

        current_version = landing_zone.get("version", "")
        latest_version = landing_zone.get("latestAvailableVersion", "")
        is_latest = current_version == latest_version and current_version != ""

        return {
            "check": "Control Tower latest version",
            "description": "Control Tower landing zone should be on the latest available version.",
            "status": "complete" if is_latest else "incomplete",
            "required": False,
            "weight": 5,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/configuration-updates.html",
        }
    except Exception as e:
        return {
            "check": "Control Tower latest version",
            "description": "Control Tower landing zone should be on the latest available version.",
            "status": "error",
            "required": False,
            "weight": 5,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/configuration-updates.html",
            "error": str(e),
        }


def run_all():
    """Run all Control Tower checks (FR-5.1 through FR-5.3)."""
    return [
        check_control_tower_deployed(),
        check_control_tower_not_drifted(),
        check_control_tower_latest_version(),
    ]
