from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"
