from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Bounded pages: clients can ask for up to 100 rows, never more."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
