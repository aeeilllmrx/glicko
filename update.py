# -*- coding: utf-8 -*-
import csv
from typing import Dict, List, Tuple

from glicko import Glicko2, Rating


class CustomDialect(csv.Dialect):
    delimiter = "\t"
    quotechar = '"'
    doublequote = True
    skipinitialspace = True
    lineterminator = "\n"
    quoting = csv.QUOTE_MINIMAL


csv.register_dialect("custom", CustomDialect)


def load_player_stats(filename: str) -> Dict[str, Tuple[str, Rating]]:
    """
    Returns a mapping from player id to (name, Rating) tuple.
    """
    player_stats = {}
    with open(filename, "r", newline="") as file:
        next(file)
        for line in file:
            parts = line.strip().split("\t")
            if len(parts) != 5:
                print(f"Skipping malformed line: {line}")
                print(len(parts))
                continue

            _id, name, rating, rd, vol = parts

            player_stats[_id] = (
                name,
                Rating(
                    mu=int(rating),
                    phi=int(rd),
                    sigma=float(vol),
                ),
            )
    return player_stats


def load_tournament_results(filename: str) -> List[Dict]:
    """
    Return a dictionary with keys {Number, ID, Name, Rnd1, Rnd2, Rnd3, Rnd4, Rnd5}.
    """
    results = []
    with open(filename, "r", newline="") as file:
        reader = csv.DictReader(file, dialect="custom")
        for i, row in enumerate(reader):
            cleaned_row = {
                k.strip(): v.strip() for k, v in row.items() if k and k.strip()
            }
            cleaned_row["Number"] = i + 1
            results.append(cleaned_row)
    return results


def parse_round_result(result: str) -> Tuple[str, int]:
    if result == "-H-" or result == "-U-":
        return ("X", -1)
    result_type = result[0]
    opponent_number = int(result[1:])
    return (result_type, opponent_number)


def update(p1: Rating, p2: Rating, result: str) -> Tuple[Rating, Rating]:
    if result == "W":
        p1, p2 = glicko2.rate_1vs1(p1, p2)
    elif result == "L":
        p2, p1 = glicko2.rate_1vs1(p2, p1)
    elif result == "D":
        p1, p2 = glicko2.rate_1vs1(p1, p2, drawn=True)
    else:
        print(f"Error: Invalid game result '{result}'. Skipping game.")

    return p1, p2


def process_round(
    player_results: List[Dict],
    player_stats: Dict,
    player_lookup: Dict,
    round_number: int,
):
    for player in player_results:
        result = player[f"Rnd{round_number}"]
        result_type, opponent_number = parse_round_result(result)

        if result_type != "X":  # Ignore byes and unplayed games
            p1_id = player["ID"]
            p1_data = player_stats.get(p1_id)
            if p1_data is None:
                print(f"Error: Player {p1_id} not found in player stats.")
                continue
            p1_name, p1_rating = p1_data

            opponent = player_lookup.get(opponent_number)
            if opponent is None:
                print(f"Warning: Opponent {opponent_number} not found")
                continue

            p2_id = opponent["ID"]
            p2_data = player_stats.get(p2_id)
            if p2_data is None:
                print(f"Error: Player {p2_id} not found in player stats.")
                continue
            p2_name, p2_rating = p2_data

            p1_rating_updated, p2_rating_updated = update(
                p1_rating, p2_rating, result_type
            )

            player_stats[p1_id] = (p1_name, p1_rating_updated)
            player_stats[p2_id] = (p2_name, p2_rating_updated)


def save_player_stats(results: Dict, output_file: str):
    try:
        with open(output_file, "w", newline="") as file:
            writer = csv.writer(file, dialect="custom")
            writer.writerow(["ID", "name", "rating", "RD", "vol"])
            for _id, (name, rating) in results.items():
                writer.writerow(
                    [
                        _id,
                        name,
                        round(rating.mu),
                        round(rating.phi),
                        round(rating.sigma, 6),
                    ]
                )
        print(f"Updated ratings have been written to {output_file}")
    except IOError as e:
        print(f"Error writing to output file: {e}")


def process_tournament(players_file: str, games_file: str, output_file: str):
    player_stats = load_player_stats(players_file)
    player_results = load_tournament_results(games_file)
    player_lookup = {int(p["Number"]): p for p in player_results}

    for round_number in range(1, 6):  # 5 rounds
        process_round(player_results, player_stats, player_lookup, round_number)

    save_player_stats(player_stats, output_file)


if __name__ == "__main__":
    import sys

    glicko2 = Glicko2()

    if len(sys.argv) != 4:
        print("Usage: python update.py players.csv games.csv output.csv")
    else:
        process_tournament(sys.argv[1], sys.argv[2], sys.argv[3])
