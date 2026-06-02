from typing import Any


class DomainError(Exception):
    status_code: int = 500
    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


# === Auth ===
class InvalidTokenError(DomainError):
    status_code = 401
    code = "INVALID_TOKEN"

    def __init__(self) -> None:
        super().__init__("유효하지 않은 토큰입니다")


class InvalidCredentialsError(DomainError):
    status_code = 401
    code = "INVALID_CREDENTIALS"

    def __init__(self) -> None:
        super().__init__("아이디 또는 비밀번호가 올바르지 않습니다")


# === User ===
class UserNotFoundError(DomainError):
    status_code = 404
    code = "USER_NOT_FOUND"

    def __init__(self, *, user_id: str) -> None:
        super().__init__("사용자를 찾을 수 없습니다", user_id=user_id)


class DuplicateUserNameError(DomainError):
    status_code = 409
    code = "DUPLICATE_USER_NAME"

    def __init__(self, *, user_name: str) -> None:
        super().__init__("이미 사용 중인 사용자 이름입니다", user_name=user_name)


# === Event ===
class EventNotFoundError(DomainError):
    status_code = 404
    code = "EVENT_NOT_FOUND"

    def __init__(self, *, event_id: str) -> None:
        super().__init__("행사를 찾을 수 없습니다", event_id=event_id)


# === Reservation ===
class ReservationNotFoundError(DomainError):
    status_code = 404
    code = "RESERVATION_NOT_FOUND"

    def __init__(self, *, reservation_id: str) -> None:
        super().__init__("예매를 찾을 수 없습니다", reservation_id=reservation_id)


class SeatAlreadyTakenError(DomainError):
    status_code = 409
    code = "SEAT_ALREADY_TAKEN"

    def __init__(self, *, event_id: str, reserved_num: int) -> None:
        super().__init__(
            "이미 선점된 좌석입니다",
            event_id=event_id,
            reserved_num=reserved_num,
        )


class SeatOutOfRangeError(DomainError):
    status_code = 400
    code = "SEAT_OUT_OF_RANGE"

    def __init__(self, *, event_id: str, reserved_num: int, total_seats: int) -> None:
        super().__init__(
            "존재하지 않는 좌석 번호입니다",
            event_id=event_id,
            reserved_num=reserved_num,
            total_seats=total_seats,
        )


class EventSoldOutError(DomainError):
    status_code = 409
    code = "EVENT_SOLD_OUT"

    def __init__(self, *, event_id: str) -> None:
        super().__init__("해당 행사의 좌석이 모두 매진되었습니다", event_id=event_id)
