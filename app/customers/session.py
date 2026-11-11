"""Who is on this call, and does the order have somewhere to go?

A `CustomerContext` is what we already know about the caller, read once when the session
starts (one database round trip, keyed by their phone number and the store). A
`CustomerSession` is the live state of the call: it adds what the caller tells us now, and
answers the one question checkout asks, "is this order ready to place?".

  returning customer, address saved -> ready; the agent never asks for it
  new customer, delivery order      -> not ready until name and address are captured
  pickup, or a guest at a table     -> ready

The rule lives here, in code, so the model can't skip it: the checkout tool consults
`delivery_ready()` and holds the order, the same way it holds for the dessert offer.
"""
import logging
from dataclasses import dataclass, field

from app.customers import repository
from app.customers.phone import mask_phone, normalize_phone

logger = logging.getLogger("sarthi.customers")


@dataclass(frozen=True)
class CustomerContext:
    known: bool = False
    customer_id: str | None = None
    name: str | None = None
    language: str | None = None
    address: dict | None = None  # {"id", "line", "area", "landmark", "pincode"}
    order_count: int = 0
    last_items: tuple[str, ...] = ()  # names from the last order, e.g. ("Dolo 650 Tablet", "ORS Orange")

    @staticmethod
    def from_row(row: dict | None) -> "CustomerContext":
        """Build from the customer_context() database function's JSON; None means a new caller."""
        if not row or not row.get("customer"):
            return CustomerContext()
        customer = row["customer"]
        items = ((row.get("last_order") or {}).get("items")) or []
        names = tuple(dict.fromkeys(i["name"] for i in items if isinstance(i, dict) and i.get("name")))
        return CustomerContext(
            known=True,
            customer_id=customer.get("id"),
            name=(customer.get("name") or None),
            language=customer.get("language"),
            address=row.get("address") or None,
            order_count=int(row.get("order_count") or 0),
            last_items=names,
        )


def load_context(restaurant_id: str, phone: str) -> CustomerContext:
    """The caller's saved profile, or an empty context. A lookup failure (database down, or the
    migration not applied yet) must never stop the call, so it counts as a new caller."""
    try:
        return CustomerContext.from_row(repository.customer_context(restaurant_id, phone))
    except Exception:
        logger.warning("customer lookup failed for %s; treating as new", mask_phone(phone), exc_info=True)
        return CustomerContext()


@dataclass
class CustomerSession:
    restaurant_id: str
    phone: str | None  # E.164, or None when caller ID is withheld (the call then can't be remembered)
    context: CustomerContext = field(default_factory=CustomerContext)
    delivery_required: bool = True
    language: str = "en"
    name: str | None = None  # told to us on this call
    address: dict | None = None  # told to us on this call
    fulfilment: str | None = None  # "pickup" once chosen
    customer_id: str | None = None  # known from the start, or created when details are saved
    awaiting_confirm: bool = False  # the address (or pickup) was just taken: the customer must confirm it first
    phone_verified: bool = False  # caller ID or a WhatsApp sender, never a number typed into a web page
    rx_path: str | None = None  # "whatsapp" or "pharmacist": how a prescription order gets its prescription checked
    checkout_pending: bool = False  # the guest has asked to place the order, but it is waiting on a missing answer

    def __post_init__(self):
        self.customer_id = self.customer_id or self.context.customer_id

    # -- what we know ---------------------------------------------------------------------------

    def display_name(self) -> str | None:
        return self.name or self.context.name

    def current_address(self) -> dict | None:
        return self.address or self.context.address

    def delivery_ready(self) -> bool:
        """Can the order be placed? Not when it must be delivered and we have neither an address nor a pickup."""
        return not self.delivery_required or self.fulfilment == "pickup" or self.current_address() is not None

    def fulfilment_kind(self) -> str:
        if not self.delivery_required:
            return "dine_in"
        return "pickup" if self.fulfilment == "pickup" else "delivery"

    # -- what the caller tells us ---------------------------------------------------------------

    def save_details(self, name: str | None, address: dict) -> None:
        """Remember what the caller said, on this call and (when we know their number) for next time."""
        self.name = name or self.name
        self.address = address
        self.fulfilment = None
        self.awaiting_confirm = True
        if not self.phone:
            return
        try:
            self.customer_id, address_id = repository.save_details(
                self.restaurant_id, self.phone, self.display_name(), self.language, address
            )
            self.address = {**address, "id": address_id}
        except Exception:
            logger.warning("couldn't save details for %s", mask_phone(self.phone), exc_info=True)

    def choose_rx_path(self, path: str) -> None:
        self.rx_path = path

    def choose_pickup(self) -> None:
        self.fulfilment = "pickup"
        self.awaiting_confirm = True

    # -- recording the order --------------------------------------------------------------------

    def order_fields(self) -> dict:
        """Extra columns for the orders row (see erp.record_order). Only what is known is included."""
        fields: dict = {"fulfilment": self.fulfilment_kind()}
        if self.rx_path:
            fields["rx_path"] = self.rx_path
        if self.customer_id:
            fields["customer_id"] = self.customer_id
        if self.phone:
            fields["caller_phone"] = self.phone
        if self.fulfilment_kind() == "delivery" and self.current_address():
            fields["address_snapshot"] = {k: v for k, v in self.current_address().items() if k != "id" and v}
        return fields

    # -- what the model is told -----------------------------------------------------------------

    def prompt_block(self) -> str:
        if not self.delivery_required and not self.context.known:
            return ""
        lines = ["", "THE CALLER"]
        if self.context.known:
            who = self.context.name or "a returning customer"
            lines.append(
                f"This is a returning customer: {who}. Greet them by name if you have it, and offer once, in one "
                "short line, to repeat their last order."
            )
            if self.context.last_items:
                lines.append(f"Their last order: {', '.join(self.context.last_items)}.")
            area = (self.context.address or {}).get("area")
            if self.delivery_required and self.context.address:
                lines.append(
                    "Their delivery address is already saved. NEVER ask for it. When you place the order, say it "
                    + (f"will go to their address in {area}" if area else "will go to their saved address")
                    + ". If they give a different address, call save_delivery_details with it."
                )
        elif self.delivery_required:
            lines.append("This caller is new to us.")
        if self.delivery_required and not self.context.address:
            lines.append(
                "Do not ask for an address while they are choosing items. Once they have said they are done, and "
                "before you place the order, ask in one line for their name and full delivery address (house or flat, "
                "street, area, a landmark), or whether they would rather pick it up. Then call save_delivery_details "
                "(or choose_pickup), read the address back once and ask them to confirm. Only then place the order. "
                "Never invent or guess an address."
            )
        return "\n".join(lines)


def start_session(
    restaurant: dict, phone_raw: str | None, table_no: str | None, language: str = "en", verified: bool = False
) -> CustomerSession | None:
    """The customer side of a new call or chat for `restaurant`, or None when there is nothing to do.

    Kirana and pharmacy orders are always delivered, so they always need an address. A restaurant
    guest at a table needs none; a restaurant order over the phone (no table) is a delivery.
    A phone number, when we have one, lets us recognise a returning customer.

    `verified` says the number can be trusted: a real call's caller ID, or the sender of a WhatsApp
    message. A number typed into a web page is NOT verified: anyone could type someone else's number and
    be greeted with their name and area. So it is ignored, unless the store is a demo store
    (`demo_mode`, set in the database) where trying a returning customer in the browser is the point.
    """
    if phone_raw and not verified and not restaurant.get("demo_mode"):
        phone_raw = None
    phone = normalize_phone(phone_raw)
    business_type = restaurant.get("business_type") or "restaurant"
    delivery = business_type != "restaurant" or (table_no is None and phone is not None)
    if not delivery and phone is None:
        return None
    context = load_context(restaurant["id"], phone) if phone else CustomerContext()
    return CustomerSession(
        restaurant["id"], phone, context, delivery_required=delivery, language=language, phone_verified=bool(phone) and verified
    )


def needs_identification(current: CustomerSession | None, fresh: CustomerSession | None) -> bool:
    """Did a caller's number arrive after the chat began as an anonymous guest? (A web guest types it in
    when they start a call.) Then the chat starts over as that caller, keeping the cart."""
    return fresh is not None and fresh.phone is not None and (current is None or current.phone is None)
