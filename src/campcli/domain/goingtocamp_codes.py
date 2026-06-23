"""GoingToCamp API constants — category/equipment/availability codes.

Validated by the prior investigation in test-report.md. All IDs are large
negative ints by GoingToCamp convention.
"""
CAMP_SITE = -2147483648
OVERFLOW_SITE = -2147483647
GROUP_SITE = -2147483643
CAMP_CATEGORY_IDS = (CAMP_SITE, OVERFLOW_SITE, GROUP_SITE)

NON_GROUP_EQUIPMENT = -32768

AVAILABILITY_AVAILABLE = 0
AVAILABILITY_RESERVED = 1
AVAILABILITY_CLOSED = 2
AVAILABILITY_WALK_IN = 3
