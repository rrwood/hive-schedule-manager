"""Constants for the Hive Schedule Manager integration."""

DOMAIN = "hive_schedule"

# Hive AWS Cognito configuration
COGNITO_POOL_ID = "eu-west-1_SamNfoWtf"
COGNITO_CLIENT_ID = "3rl4i0ajrmtdm8sbre54p9dvd9"
COGNITO_REGION = "eu-west-1"

# Configuration
CONF_MFA_CODE = "mfa_code"
CONF_ID_TOKEN = "id_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRY = "token_expiry"

# Service names
SERVICE_SET_DAY = "set_day_schedule"

# Attributes
ATTR_NODE_ID = "node_id"
ATTR_DAY = "day"
ATTR_SCHEDULE = "schedule"
ATTR_PROFILE = "profile"

# Schedule profiles
PROFILE_WEEKDAY = "weekday"
PROFILE_WEEKEND = "weekend"
PROFILE_HOLIDAY = "holiday"
PROFILE_CUSTOM = "custom"

# Hive API
HIVE_API_URL = "https://beekeeper.hivehome.com/1.0"