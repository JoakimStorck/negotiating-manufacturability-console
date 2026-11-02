"""The order tool: a product's requirements stated by an established method, checked, and bound to a design's features.

    from am_order import Home, Order, check, bind, render, export

    home = Home("products")                       # a products home (or AM_ORDER_HOME)
    order = home.load("bracket-ge")               # the order as it stands; "bracket-ge@2" a revision of it
    refusals = check(order, features=home.features(order.data["design"]))
    report = bind(order, home.features("bracket-ge@v4"))
    text = render(order, "markdown")
    export(order, "xlsx", "bracket-ge.xlsx")

Every other interface (the command line, the web app) calls only this. The contracts with a design system are the two schemas,
`schemas/order-1.json` and `schemas/features-1.json`.
"""
from .bind import bind, confirm, proposals, reject
from .check import Refusal, check
from .diff import diff
from .export import export, import_xlsx, read_reqif
from .home import Home, HomeError, ReadOnly, Refused, Saved
from .order import Order
from .render import render, table
from .schema import SchemaError, validate_features, validate_order

__version__ = "1.0.0"
__all__ = ["Home", "Order", "check", "bind", "render", "export", "import_xlsx", "read_reqif", "confirm", "reject", "proposals", "diff",
           "table", "Refusal", "HomeError", "ReadOnly", "Refused", "Saved", "SchemaError", "validate_order", "validate_features"]
