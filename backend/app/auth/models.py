import enum


class UserRole(str, enum.Enum):
    SUPER_ADMINISTRATOR = "super_administrator"
    ADMINISTRATOR = "administrator"
    LEAD_INVESTIGATOR = "lead_investigator"
    INVESTIGATOR = "investigator"
    ANALYST = "analyst"
    READ_ONLY_VIEWER = "read_only_viewer"
