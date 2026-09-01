from kidneymatch.compensation.models import CompensationRequest


def test_rial_to_toman_is_integer_conversion() -> None:
    request = CompensationRequest(donor_id="synthetic-donor", amount_rial=6_000_000_000)
    assert request.amount_toman == 600_000_000
