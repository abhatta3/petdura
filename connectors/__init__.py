from .mock_flights import (
    BudgetWingsMock,
    CloudHopperMock,
    NorthStarAirMock,
    SkyPathMock,
)

ALL_CONNECTORS = [
    SkyPathMock(),
    CloudHopperMock(),
    BudgetWingsMock(),
    NorthStarAirMock(),
]
