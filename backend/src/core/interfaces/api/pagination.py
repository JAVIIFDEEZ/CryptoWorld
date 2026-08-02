"""
interfaces/api/pagination.py — Paginación estándar de los listados.

Los endpoints de listado volcaban la tabla entera en cada respuesta:
`/api/admin/users/` con la base de datos poblada devuelve tantas filas
como usuarios haya. Además del coste en memoria del proceso web, es un
vector de denegación de servicio trivial.

`StandardPagination` fija un tamaño de página por defecto y, sobre todo,
un techo (`max_page_size`) que el cliente no puede sobrepasar.

`paginate_list` es el ayudante para las vistas basadas en `APIView`, que
—a diferencia de las genéricas de DRF— no paginan solas.
"""

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Paginación por número de página: ?page=2&page_size=25."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("page", self.page.number),
                    ("page_size", self.get_page_size(self.request)),
                    ("total_pages", self.page.paginator.num_pages),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )


def paginate_list(request, queryset, serialize, view=None) -> Response:
    """
    Paginar un queryset desde una `APIView` y devolver la respuesta.

    Args:
        request: la petición DRF en curso.
        queryset: queryset (o lista) ya ordenado.
        serialize: callable que recibe la página y devuelve datos serializables.
        view: la vista, para que DRF pueda construir los enlaces next/previous.

    Returns:
        Response con la envolvente estándar de paginación.
    """
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serialize(page))
