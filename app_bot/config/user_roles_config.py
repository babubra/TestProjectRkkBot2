from app_bot.database.models import Permission


USER_ROLE_PERMISSIONS = [
    Permission.CREATE_TICKETS,
    Permission.VIEW_TICKETS,
]

GEODESIST_ROLE_PERMISSIONS = USER_ROLE_PERMISSIONS + [
    # Permission.SET_TRIP_LIMITS, # Как правило, геодезисты не управляют лимитами
    Permission.ADD_FILES_FROM_VISIT,
]

MANAGER_ROLE_PERMISSIONS = USER_ROLE_PERMISSIONS + [
    Permission.SET_TRIP_LIMITS,
]


ADMIN_ROLE_PERMISSIONS = list(
    set(MANAGER_ROLE_PERMISSIONS + GEODESIST_ROLE_PERMISSIONS + [Permission.MANAGE_USERS])
)
