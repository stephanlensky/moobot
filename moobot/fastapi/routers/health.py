from fastapi import APIRouter, Response, status

router = APIRouter(prefix="/health")


@router.get("")
@router.head("")
def get_health() -> Response:
    return Response(status_code=status.HTTP_200_OK)
