from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """อนุญาตเฉพาะผู้ใช้ role='staff' (เจ้าหน้าที่) เท่านั้น"""

    message = "การทำรายการนี้ต้องเป็นเจ้าหน้าที่เท่านั้น"

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.STAFF)


class IsStudentUser(BasePermission):
    """อนุญาตเฉพาะผู้ใช้ role='student' (นักศึกษา) เท่านั้น"""

    message = "การทำรายการนี้ต้องเป็นนักศึกษาเท่านั้น"

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.STUDENT)
