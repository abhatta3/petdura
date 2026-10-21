"""
Connector interface that every "site" plugs into.

Each connector represents one external source (a vendor, a search engine, an
API). The aggregator in app.py only ever calls `.search(parsed_query)` and
expects a list of plain dicts back with a common schema, so adding a new
source never touches the parser, the aggregator, or the frontend.
"""


class BaseConnector:
    name = "base"

    def search(self, parsed_query):
        raise NotImplementedError
