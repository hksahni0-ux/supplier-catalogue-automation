from fci.cli import main
from fci.grid import format_grid, price_grid

ROWS = [
    {"code": "x-1", "combo": "A - W.1 X D.2 X H.3 cm [+] ECP01 BIANCO", "price": "4121"},
    {"code": "x-1", "combo": "A - W.1 X D.2 X H.3 cm [+] ECP05 TORTORA", "price": "4121"},
    {"code": "x-1", "combo": "A - W.1 X D.2 X H.3 cm [+] B240", "price": "4498"},
    {"code": "x-1", "combo": "B - W.1 X D.2 X H.3 cm [+] ECP01 BIANCO", "price": "4122"},
]


def test_grid_collapses_rows_to_one_price_per_size_and_group() -> None:
    grid = price_grid(ROWS)
    assert list(grid) == ["A - W.1 X D.2 X H.3 cm", "B - W.1 X D.2 X H.3 cm"]
    assert grid["A - W.1 X D.2 X H.3 cm"] == {4121: ["ECP01 BIANCO", "ECP05 TORTORA"], 4498: ["B240"]}


def test_format_lists_prices_low_to_high_with_counts() -> None:
    text = format_grid(price_grid(ROWS))
    assert "3 distinct prices" in text
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if "4121" in line)
    assert "2 covers" in lines[first] and "ECP01 BIANCO" in lines[first]
    assert first < next(i for i, line in enumerate(lines) if "4498" in line)


def test_cli_grid_reads_a_prices_csv(tmp_path, capsys) -> None:
    path = tmp_path / "x-1-prices.csv"
    path.write_text("code,combo,price\n" + "\n".join(f"{r['code']},{r['combo']},{r['price']}" for r in ROWS))
    assert main(["grid", str(path)]) == 0
    assert "4498" in capsys.readouterr().out
