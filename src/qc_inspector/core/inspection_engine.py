"""
inspection_engine.py
Logica di valutazione PASS/FAIL per controlli dimensionali e Sì/No.
"""

from typing import Optional, Tuple

from .app_config import format_decimal


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_DEROGATION = "ACCETTATO IN DEROGA"
STATUS_INCOMPLETE = "INCOMPLETO"
STATUS_EMPTY = "NESSUNA MISURA"

CRITICALITY_PREFIXES = {
    "C": "critical",
    "I": "important",
    "N": "normal",
}


def evaluate_dimensional(value: float, nominal: float,
                          tol_plus: float, tol_minus: float) -> Tuple[bool, str]:
    """
    Valuta un controllo dimensionale.
    Restituisce (pass_fail, messaggio).
    """
    lower = nominal - abs(tol_minus)
    upper = nominal + abs(tol_plus)

    if lower <= value <= upper:
        deviation = value - nominal
        return True, f"PASS  ({format_decimal(deviation, signed=True)})"
    else:
        deviation = value - nominal
        if value < lower:
            return False, (
                f"FAIL  ({format_decimal(deviation, signed=True)}  — "
                f"sotto il minimo {format_decimal(lower)})"
            )
        else:
            return False, (
                f"FAIL  ({format_decimal(deviation, signed=True)}  — "
                f"sopra il massimo {format_decimal(upper)})"
            )


def evaluate_yesno(value: bool, expected: bool = True) -> Tuple[bool, str]:
    """
    Valuta un controllo Sì/No.
    Di default il risultato atteso è Sì (presenza).
    """
    result = (value == expected)
    label = "Sì" if value else "No"
    return result, f"{'PASS' if result else 'FAIL'}  (risposta: {label})"


def evaluate_control(control: dict, value_num: Optional[float],
                     value_bool: Optional[bool]) -> Tuple[bool, str]:
    """
    Dispatcher: valuta il controllo in base al tipo.
    control: dizionario da DB con campi control_type, nominal, tol_plus, tol_minus
    """
    if control["control_type"] == "dimensional":
        if value_num is None:
            return False, "FAIL  (nessun valore inserito)"
        return evaluate_dimensional(
            value_num,
            control["nominal"],
            control["tol_plus"],
            control["tol_minus"]
        )
    elif control["control_type"] == "yesno":
        if value_bool is None:
            return False, "FAIL  (nessuna risposta)"
        return evaluate_yesno(value_bool)
    else:
        return False, "FAIL  (tipo controllo sconosciuto)"


def get_measurement_status(measurement: dict) -> str:
    """Restituisce l'esito effettivo senza perdere la conformità tecnica."""
    if bool(measurement.get("pass_fail")):
        return STATUS_PASS
    if bool(measurement.get("accepted_in_derogation")):
        return STATUS_DEROGATION
    return STATUS_FAIL


def get_control_status(measurements: list) -> Optional[str]:
    """Aggrega le misure di un controllo, dando priorità ai FAIL aperti."""
    if not measurements:
        return None
    statuses = [get_measurement_status(m) for m in measurements]
    if STATUS_FAIL in statuses:
        return STATUS_FAIL
    if STATUS_DEROGATION in statuses:
        return STATUS_DEROGATION
    return STATUS_PASS


def get_lot_status(measurements: list) -> Tuple[str, str]:
    """
    Valuta l'esito complessivo del lotto.
    Un FAIL accettato in deroga resta tecnicamente fallito, ma non lascia
    una non conformità aperta sul lotto.
    """
    if not measurements:
        return STATUS_EMPTY, "Nessuna misura registrata"

    total = len(measurements)
    failed = sum(1 for m in measurements if get_measurement_status(m) == STATUS_FAIL)
    derogated = sum(
        1 for m in measurements
        if get_measurement_status(m) == STATUS_DEROGATION
    )

    if failed:
        return STATUS_FAIL, f"LOTTO FAIL  —  {failed}/{total} controlli falliti"
    if derogated:
        return (
            STATUS_DEROGATION,
            f"LOTTO ACCETTATO IN DEROGA  —  {derogated}/{total} controlli derogati"
        )
    return STATUS_PASS, f"LOTTO PASS  —  {total}/{total} controlli superati"


def get_lot_result(measurements: list) -> Tuple[bool, str]:
    """Compatibilità: True per PASS o lotto interamente accettato in deroga."""
    status, message = get_lot_status(measurements)
    return status in {STATUS_PASS, STATUS_DEROGATION}, message


def get_sampling_requirements(lot: dict) -> dict[str, dict[str, int]]:
    """Restituisce lo snapshot n/Ac/Re del lotto, con fallback legacy."""
    legacy_n = max(1, int(lot.get("n_samples") or 1))
    requirements: dict[str, dict[str, int]] = {}
    for criticality, prefix in CRITICALITY_PREFIXES.items():
        raw_n = lot.get(f"{prefix}_n")
        raw_ac = lot.get(f"{prefix}_ac")
        raw_re = lot.get(f"{prefix}_re")
        if raw_n is None or raw_ac is None or raw_re is None:
            requirements[criticality] = {"n": legacy_n, "ac": 0, "re": 1}
        else:
            requirements[criticality] = {
                "n": max(1, int(str(raw_n))),
                "ac": max(0, int(str(raw_ac))),
                "re": max(1, int(str(raw_re))),
            }
    return requirements


def get_control_sample_count(lot: dict, control: dict) -> int:
    criticality = control.get("criticality") or "N"
    requirements = get_sampling_requirements(lot)
    requirement = (
        requirements[criticality]
        if criticality in requirements else requirements["N"]
    )
    return requirement["n"]


def get_expected_measurement_count(lot: dict, controls: list) -> int:
    requirements = get_sampling_requirements(lot)
    total = 0
    for control in controls:
        criticality = control.get("criticality") or "N"
        requirement = (
            requirements[criticality]
            if criticality in requirements else requirements["N"]
        )
        total += requirement["n"]
    return total


def get_required_controls_for_sample(
        lot: dict, controls: list, sample_num: int) -> list:
    """Controlli applicabili a uno specifico pezzo del campione."""
    requirements = get_sampling_requirements(lot)
    required = []
    for control in controls:
        criticality = control.get("criticality") or "N"
        requirement = (
            requirements[criticality]
            if criticality in requirements else requirements["N"]
        )
        if sample_num <= requirement["n"]:
            required.append(control)
    return required


def evaluate_sampling_lot(
        lot: dict, controls: list, measurements: list) -> dict:
    """Valuta completezza ed esito del lotto applicando n, Ac e Re.

    I difettosi sono contati per pezzo e criticità: più quote fallite della
    stessa criticità sullo stesso campione valgono come un solo difettoso.
    """
    requirements = get_sampling_requirements(lot)
    controls_by_id = {control["id"]: control for control in controls}
    measurement_map = {
        (measurement["control_id"], int(measurement["sample_num"])): measurement
        for measurement in measurements
        if measurement.get("control_id") in controls_by_id
    }
    expected_total = get_expected_measurement_count(lot, controls)
    completed_total = 0
    by_criticality = {}

    for criticality in ("C", "I", "N"):
        category_controls = [
            control for control in controls
            if (control.get("criticality") or "N") == criticality
        ]
        requirement = requirements[criticality]
        expected = requirement["n"] * len(category_controls)
        completed = sum(
            1
            for control in category_controls
            for sample_num in range(1, requirement["n"] + 1)
            if (control["id"], sample_num) in measurement_map
        )
        completed_total += completed

        defective = open_defective = derogated_defective = 0
        for sample_num in range(1, requirement["n"] + 1):
            sample_measurements = [
                measurement_map[(control["id"], sample_num)]
                for control in category_controls
                if (control["id"], sample_num) in measurement_map
            ]
            has_defect = any(
                not bool(measurement.get("pass_fail"))
                for measurement in sample_measurements
            )
            has_open_defect = any(
                not bool(measurement.get("pass_fail"))
                and not bool(measurement.get("accepted_in_derogation"))
                for measurement in sample_measurements
            )
            if has_defect:
                defective += 1
                if has_open_defect:
                    open_defective += 1
                else:
                    derogated_defective += 1

        category_complete = expected == 0 or completed >= expected
        reached_re = defective >= requirement["re"]
        rejected = reached_re or (
            category_complete and defective > requirement["ac"]
        )
        by_criticality[criticality] = {
            **requirement,
            "controls": len(category_controls),
            "expected": expected,
            "completed": completed,
            "complete": category_complete,
            "defective": defective,
            "open_defective": open_defective,
            "derogated_defective": derogated_defective,
            "reached_re": reached_re,
            "rejected": rejected,
        }

    complete = expected_total > 0 and completed_total >= expected_total
    active_categories = [
        data for data in by_criticality.values() if data["controls"]
    ]
    rejected_categories = [data for data in active_categories if data["rejected"]]
    open_rejections = [
        data for data in rejected_categories if data["open_defective"]
    ]
    if not measurement_map:
        status = STATUS_EMPTY
        message = "Nessuna misura registrata"
    elif open_rejections:
        status = STATUS_FAIL
        message = "LOTTO FAIL — superata la soglia Ac"
    elif not complete:
        status = STATUS_INCOMPLETE
        message = (
            f"CONTROLLO IN CORSO — {completed_total}/{expected_total} misure"
        )
    elif rejected_categories:
        status = STATUS_DEROGATION
        message = "LOTTO ACCETTATO IN DEROGA — superata la soglia Ac"
    else:
        status = STATUS_PASS
        message = "LOTTO PASS — difettosi entro le soglie Ac"

    return {
        "status": status,
        "message": message,
        "complete": complete,
        "expected_total": expected_total,
        "completed_total": completed_total,
        "by_criticality": by_criticality,
    }


def format_tolerance(nominal: float, tol_plus: float, tol_minus: float) -> str:
    """Formatta la quota come stringa leggibile: 25.000 +0.050/-0.050"""
    return (
        f"{format_decimal(nominal)}  "
        f"+{format_decimal(tol_plus)}/-{format_decimal(tol_minus)}"
    )


def get_control_limits(control: dict) -> Tuple[Optional[float], Optional[float]]:
    """Restituisce (limite_inferiore, limite_superiore) per controlli dimensionali."""
    if control["control_type"] != "dimensional":
        return None, None
    lower = control["nominal"] - abs(control["tol_minus"])
    upper = control["nominal"] + abs(control["tol_plus"])
    return lower, upper
