"""How much electricity a print actually draws.

A printer does not pull its rated wattage for the whole job. The bed and the hotend
spend most of the time holding a temperature rather than reaching it, and how hard they
work follows the temperature the file asks for: a 60 °C PLA plate and a 110 °C ABS plate
on the same machine are not the same electricity bill. Charging every print at the rated
figure overstates the cool ones and understates the hot ones.
"""

# Share of its rated power a heater averages over a print, by the temperature it holds.
# The bands are deliberately coarse: this is an estimate that beats a flat figure, not a
# measurement, and pretending otherwise would invite trust it has not earned.
_BED_DUTY_BANDS = ((45.0, 0.15), (70.0, 0.30), (95.0, 0.45))
_BED_DUTY_ABOVE = 0.60
_NOZZLE_DUTY_BANDS = ((220.0, 0.10), (260.0, 0.15))
_NOZZLE_DUTY_ABOVE = 0.20

# Motors idle between moves but are never switched off; electronics, display and fans
# run for the whole job.
_STEPPER_DUTY = 0.35
_ELECTRONICS_DUTY = 1.0


def _duty(
    temperature_c: float | None,
    bands: tuple[tuple[float, float], ...],
    above: float,
) -> float:
    """Duty share for a heater holding this temperature.

    An unknown temperature takes the middle band rather than zero: a manually entered
    job has no file to read temperatures from, and treating the heaters as switched off
    would be a worse answer than assuming an ordinary print.
    """
    if temperature_c is None or temperature_c <= 0:
        return bands[len(bands) // 2][1]
    for limit, share in bands:
        if temperature_c <= limit:
            return share
    return above


def average_power_w(
    *,
    hotend_w: float | None,
    bed_w: float | None,
    steppers_w: float | None,
    electronics_w: float | None,
    nozzle_temperature_c: float | None = None,
    bed_temperature_c: float | None = None,
    fallback_w: float | None = None,
) -> float | None:
    """Average draw over a print, or the flat rated figure when the parts are unknown.

    Nobody is required to open their printer and measure four numbers, so a machine
    described only by its total wattage keeps costing exactly what it used to.
    """
    parts = (hotend_w or 0.0, bed_w or 0.0, steppers_w or 0.0, electronics_w or 0.0)
    if not any(parts):
        return fallback_w

    hotend, bed, steppers, electronics = parts
    return (
        hotend * _duty(nozzle_temperature_c, _NOZZLE_DUTY_BANDS, _NOZZLE_DUTY_ABOVE)
        + bed * _duty(bed_temperature_c, _BED_DUTY_BANDS, _BED_DUTY_ABOVE)
        + steppers * _STEPPER_DUTY
        + electronics * _ELECTRONICS_DUTY
    )
