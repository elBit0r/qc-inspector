"""Valori predefiniti e regole dei piani di campionamento in ingresso."""

from datetime import datetime, timedelta


SAMPLING_PLAN_COLUMNS = (
    "lot_min", "lot_max",
    "critical_n", "critical_ac", "critical_re",
    "important_n", "important_ac", "important_re",
    "normal_n", "normal_ac", "normal_re",
)

SAMPLING_PLAN_LABELS = (
    "Lotto min", "Lotto max",
    "C · n", "C · Ac", "C · Re",
    "I · n", "I · Ac", "I · Re",
    "N · n", "N · Ac", "N · Re",
)

SAMPLING_PLAN_DESCRIPTIONS = {
    "ESTESO": (
        "Nuovo articolo/fornitore, modifica processo, non conformità recente "
        "o rischio elevato."
    ),
    "NORMALE": (
        "Condizione standard per fornitore/articolo qualificato e stabile."
    ),
    "RIDOTTO": (
        "Storico consolidato, assenza di non conformità significative e "
        "performance positiva del fornitore."
    ),
}


def recommend_sampling_profile(
        history: list[dict], rules: dict,
        reference_date: datetime | None = None) -> dict:
    """Suggerisce ESTESO/NORMALE/RIDOTTO dallo storico già filtrato."""
    now = reference_date or datetime.now()
    validity_days = max(1, int(rules.get("history_validity_days") or 730))
    extended_required = max(
        1, int(rules.get("extended_passes_required") or 1)
    )
    normal_required = max(
        1, int(rules.get("normal_passes_required") or 2)
    )
    fail_resets = bool(rules.get("fail_resets_extended", 1))
    derogation_positive = bool(rules.get("derogation_counts_positive", 0))

    completed = []
    for lot in history:
        if not lot.get("closed") or lot.get("cancelled"):
            continue
        profile = lot.get("sampling_profile")
        if profile not in {"ESTESO", "NORMALE", "RIDOTTO"}:
            continue
        try:
            created_at = datetime.fromisoformat(str(lot.get("created_at")))
        except (TypeError, ValueError):
            continue
        completed.append((created_at, lot))
    completed.sort(key=lambda item: item[0])

    if not completed:
        return {
            "profile": "ESTESO",
            "reason": "nessun controllo precedente concluso",
            "last_date": None,
        }

    last_date = completed[-1][0]
    cutoff = now - timedelta(days=validity_days)
    recent = [(date, lot) for date, lot in completed if date >= cutoff]
    if not recent:
        return {
            "profile": "ESTESO",
            "reason": (
                f"ultimo controllo più vecchio di {validity_days} giorni"
            ),
            "last_date": last_date,
        }

    def is_positive(lot: dict) -> bool:
        result = str(lot.get("result") or "").upper()
        return result == "PASS" or (
            derogation_positive and result == "ACCETTATO IN DEROGA"
        )

    sequence = []
    for date, lot in recent:
        if is_positive(lot):
            sequence.append((date, lot))
        elif fail_resets:
            sequence = []

    if not sequence:
        return {
            "profile": "ESTESO",
            "reason": "nessun esito positivo valido dopo l'ultimo esito negativo",
            "last_date": recent[-1][0],
        }

    # La progressione dipende dal tratto finale cronologico dello stesso
    # profilo. Un profilo successivo interrompe il conteggio del precedente:
    # un vecchio RIDOTTO non può quindi prevalere su un ESTESO/NORMALE recente.
    latest_profile = sequence[-1][1]["sampling_profile"]
    trailing_passes = 0
    for _, lot in reversed(sequence):
        if lot["sampling_profile"] != latest_profile:
            break
        trailing_passes += 1

    if latest_profile == "RIDOTTO":
        profile = "RIDOTTO"
        reason = "ultimo controllo positivo eseguito in piano Ridotto"
    elif latest_profile == "NORMALE" and trailing_passes >= normal_required:
        profile = "RIDOTTO"
        reason = f"{trailing_passes} controlli Normali positivi consecutivi"
    elif latest_profile == "NORMALE":
        profile = "NORMALE"
        reason = (
            f"{trailing_passes}/{normal_required} controlli Normali positivi "
            "consecutivi necessari per il Ridotto"
        )
    elif trailing_passes >= extended_required:
        profile = "NORMALE"
        reason = f"{trailing_passes} controlli Estesi positivi consecutivi"
    else:
        profile = "ESTESO"
        reason = (
            f"{trailing_passes}/{extended_required} controlli Estesi positivi "
            "consecutivi necessari per il Normale"
        )
    return {"profile": profile, "reason": reason, "last_date": last_date}

# Ordine valori: lotto min/max, quindi n/Ac/Re per C, I e N.
SAMPLING_PLANS = {
    "ESTESO": (
        (2, 8, 8, 0, 1, 3, 0, 1, 2, 0, 1),
        (9, 15, 8, 0, 1, 5, 0, 1, 3, 0, 1),
        (16, 25, 13, 0, 1, 8, 0, 1, 5, 0, 1),
        (26, 50, 20, 0, 1, 13, 0, 1, 8, 0, 1),
        (51, 90, 32, 0, 1, 20, 0, 1, 13, 1, 2),
        (91, 150, 32, 0, 1, 20, 0, 1, 13, 1, 2),
        (151, 280, 50, 0, 1, 32, 1, 2, 20, 1, 2),
        (281, 500, 80, 0, 1, 50, 1, 2, 32, 2, 3),
        (501, 1200, 125, 0, 1, 80, 2, 3, 50, 3, 4),
        (1201, 3200, 200, 0, 1, 125, 3, 4, 80, 5, 6),
        (3201, 10000, 315, 0, 1, 200, 5, 6, 125, 7, 8),
        (10001, 999999999, 500, 0, 1, 315, 7, 8, 200, 10, 11),
    ),
    "NORMALE": (
        (2, 8, 3, 0, 1, 2, 0, 1, 2, 0, 1),
        (9, 15, 5, 0, 1, 3, 0, 1, 2, 0, 1),
        (16, 25, 8, 0, 1, 5, 0, 1, 3, 0, 1),
        (26, 50, 13, 0, 1, 8, 0, 1, 5, 0, 1),
        (51, 90, 20, 0, 1, 13, 0, 1, 8, 0, 1),
        (91, 150, 20, 0, 1, 13, 0, 1, 8, 0, 1),
        (151, 280, 32, 0, 1, 20, 0, 1, 13, 1, 2),
        (281, 500, 50, 0, 1, 32, 1, 2, 20, 1, 2),
        (501, 1200, 80, 0, 1, 50, 1, 2, 32, 2, 3),
        (1201, 3200, 125, 0, 1, 80, 2, 3, 50, 3, 4),
        (3201, 10000, 200, 0, 1, 125, 3, 4, 80, 5, 6),
        (10001, 999999999, 315, 0, 1, 200, 5, 6, 125, 7, 8),
    ),
    "RIDOTTO": (
        (2, 8, 2, 0, 1, 2, 0, 1, 1, 0, 1),
        (9, 15, 3, 0, 1, 2, 0, 1, 1, 0, 1),
        (16, 25, 5, 0, 1, 3, 0, 1, 2, 0, 1),
        (26, 50, 8, 0, 1, 5, 0, 1, 3, 0, 1),
        (51, 90, 13, 0, 1, 8, 0, 1, 5, 0, 1),
        (91, 150, 13, 0, 1, 8, 0, 1, 5, 0, 1),
        (151, 280, 20, 0, 1, 13, 0, 1, 8, 0, 1),
        (281, 500, 32, 0, 1, 20, 0, 1, 13, 1, 2),
        (501, 1200, 50, 0, 1, 32, 1, 2, 20, 1, 2),
        (1201, 3200, 80, 0, 1, 50, 1, 2, 32, 2, 3),
        (3201, 10000, 125, 0, 1, 80, 2, 3, 50, 3, 4),
        (10001, 999999999, 200, 0, 1, 125, 3, 4, 80, 5, 6),
    ),
}


def get_default_sampling_plan(profile: str) -> list[dict]:
    """Restituisce una copia modificabile del piano originale richiesto."""
    if profile not in SAMPLING_PLANS:
        raise ValueError(f"Profilo di campionamento sconosciuto: {profile}.")
    rows = []
    for values in SAMPLING_PLANS[profile]:
        row = dict(zip(SAMPLING_PLAN_COLUMNS, values))
        if row["lot_max"] == 999999999:
            row["lot_max"] = None
        rows.append(row)
    return rows


def validate_sampling_plan(profile: str, rows: list[dict]) -> None:
    """Valida intervalli e parametri di un singolo piano."""
    if profile not in SAMPLING_PLANS:
        raise ValueError(f"Profilo di campionamento sconosciuto: {profile}.")
    if not rows:
        raise ValueError(f"Il piano {profile} deve contenere almeno una riga.")
    if rows[-1].get("lot_max") is not None:
        raise ValueError(
            f"{profile}, ultima riga: Lotto max deve essere infinito (∞)."
        )

    metric_groups = ("critical", "important", "normal")
    previous_max = None
    for index, row in enumerate(rows):
        row_number = index + 1
        integer_fields = ["lot_min"] + [
            f"{group}_{suffix}"
            for group in metric_groups
            for suffix in ("n", "ac", "re")
        ]
        if row.get("lot_max") is not None:
            integer_fields.append("lot_max")
        if any(
            isinstance(row.get(field), bool)
            or not isinstance(row.get(field), int)
            for field in integer_fields
        ):
            raise ValueError(
                f"{profile}, riga {row_number}: sono ammessi solo numeri interi."
            )

        lot_min = row["lot_min"]
        lot_max = row.get("lot_max")
        if index == 0 and lot_min != 2:
            raise ValueError(
                f"{profile}, riga 1: il primo intervallo deve iniziare da 2."
            )
        if lot_min < 1:
            raise ValueError(
                f"{profile}, riga {row_number}: Lotto min deve essere positivo."
            )
        if lot_max is not None and lot_max < lot_min:
            raise ValueError(
                f"{profile}, riga {row_number}: Lotto max deve essere "
                "maggiore o uguale a Lotto min."
            )
        if lot_max is None and index != len(rows) - 1:
            raise ValueError(
                f"{profile}, riga {row_number}: infinito è consentito solo "
                "nell'ultima riga."
            )
        if index:
            expected_min = previous_max + 1
            if lot_min > expected_min:
                raise ValueError(
                    f"{profile}, tra le righe {index} e {row_number}: manca "
                    f"l'intervallo da {expected_min} a {lot_min - 1}."
                )
            if lot_min < expected_min:
                raise ValueError(
                    f"{profile}, tra le righe {index} e {row_number}: i range "
                    f"si sovrappongono; Lotto min deve essere {expected_min}."
                )

        for group in metric_groups:
            sample = row[f"{group}_n"]
            acceptance = row[f"{group}_ac"]
            rejection = row[f"{group}_re"]
            if sample < 1:
                raise ValueError(
                    f"{profile}, riga {row_number}: n deve essere almeno 1."
                )
            if acceptance < 0:
                raise ValueError(
                    f"{profile}, riga {row_number}: Ac non può essere negativo."
                )
            if rejection != acceptance + 1:
                raise ValueError(
                    f"{profile}, riga {row_number}: Re deve essere uguale "
                    "ad Ac + 1."
                )
            if acceptance >= sample or rejection > sample:
                raise ValueError(
                    f"{profile}, riga {row_number}: Ac deve essere minore di n "
                    "e Re non può superare n."
                )
            if lot_max is not None and sample > lot_max:
                raise ValueError(
                    f"{profile}, riga {row_number}: n non può superare Lotto max."
                )

        previous_max = lot_max


def validate_sampling_plans(plans: dict[str, list[dict]]) -> None:
    """Valida completezza, intervalli e parametri n/Ac/Re dei tre piani."""
    required_profiles = set(SAMPLING_PLANS)
    if set(plans) != required_profiles:
        raise ValueError("Devono essere presenti i piani ESTESO, NORMALE e RIDOTTO.")
    for profile in ("ESTESO", "NORMALE", "RIDOTTO"):
        validate_sampling_plan(profile, plans[profile])
