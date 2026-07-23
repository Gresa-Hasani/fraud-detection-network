import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
GENERATE_SCRIPT = BACKEND_DIR / "scripts" / "generate_dataset.py"


def _run_generator(output_dir: Path, seed: int = 123) -> None:
    subprocess.run(
        [
            sys.executable,
            str(GENERATE_SCRIPT),
            "--customers",
            "20",
            "--accounts",
            "24",
            "--transactions",
            "80",
            "--devices",
            "20",
            "--ip-addresses",
            "15",
            "--merchants",
            "5",
            "--phone-numbers",
            "20",
            "--email-addresses",
            "20",
            "--addresses",
            "20",
            "--fraud-rate",
            "0.1",
            "--seed",
            str(seed),
            "--output-dir",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        cwd=BACKEND_DIR,
    )


def test_generator_is_deterministic_for_a_given_seed(tmp_path: Path) -> None:
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    _run_generator(out_a, seed=123)
    _run_generator(out_b, seed=123)

    for filename in ["customers.csv", "transactions.csv", "fraud_ground_truth.csv"]:
        content_a = (out_a / filename).read_text(encoding="utf-8")
        content_b = (out_b / filename).read_text(encoding="utf-8")
        assert content_a == content_b, f"{filename} differs between two runs with the same seed"


def test_generator_produces_all_required_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "run"
    _run_generator(out_dir, seed=7)

    expected_files = [
        "customers.csv",
        "accounts.csv",
        "transactions.csv",
        "devices.csv",
        "ip_addresses.csv",
        "merchants.csv",
        "phone_numbers.csv",
        "email_addresses.csv",
        "addresses.csv",
        "customer_accounts.csv",
        "customer_devices.csv",
        "customer_phones.csv",
        "customer_emails.csv",
        "customer_addresses.csv",
        "transaction_sources.csv",
        "fraud_ground_truth.csv",
    ]
    for filename in expected_files:
        path = out_dir / filename
        assert path.exists(), f"missing {filename}"
        assert path.stat().st_size > 0, f"{filename} is empty"


def test_ground_truth_has_required_columns(tmp_path: Path) -> None:
    out_dir = tmp_path / "run"
    _run_generator(out_dir, seed=7)
    header = (out_dir / "fraud_ground_truth.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "entity_id,entity_type,fraud_scenario,expected_risk_level,fraud_group_id"
