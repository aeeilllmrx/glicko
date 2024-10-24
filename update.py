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


def load_player_stats(filename: str) -> Dict[int, Tuple[str, Rating]]:
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

            player_stats[int(_id)] = (
                name,
                Rating(
                    mu=int(rating),
                    phi=int(rd),
                    sigma=float(vol),
                ),
            )
    return player_stats


def load_tournament_results(filename: str) -> Tuple[List[Dict], List[str]]:
    """
    Returns:
        - List of dictionaries with player data
        - List of round column names in order
    """
    round_columns = []
    results = []
    with open(filename, "r", newline="") as file:
        reader = csv.DictReader(file, dialect="custom")

        for column in reader.fieldnames:
            if column:
                col = column.strip()
                if (
                    col.startswith("Rnd")
                    or col.startswith("RD")
                    or col.startswith("Round ")
                ):
                    round_columns.append(col)

        # Do not include RD, as that is rating deviation
        if "RD" in round_columns:
            round_columns.remove("RD")
        round_columns.sort(key=lambda x: int("".join(filter(str.isdigit, x))))

        for i, row in enumerate(reader):
            cleaned_row = {
                k.strip(): v.strip() for k, v in row.items() if k and k.strip()
            }
            cleaned_row["ID"] = int(cleaned_row["ID"])
            results.append(cleaned_row)
    return results, round_columns


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
    round_column: str,
):
    for player in player_results:
        result = player[round_column]
        result_type, opponent_number = parse_round_result(result)
        if result_type != "X":  # Ignore byes and unplayed games
            p1_id = player["ID"]
            p1_data = player_stats.get(p1_id)
            if p1_data is None:
                print(f"Error: Player {p1_id} not found in player stats.")
                continue
            p1_name, p1_rating = p1_data

            p2_id = opponent_number
            p2_data = player_stats[opponent_number]
            if p2_data is None:
                print(f"Error: Player {opponent_number} not found in player stats.")
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
    player_results, round_columns = load_tournament_results(games_file)

    for round_column in round_columns:
        process_round(player_results, player_stats, round_column)

    save_player_stats(player_stats, output_file)


if __name__ == "__main__":
    glicko2 = Glicko2()

    players_file = "players.csv"
    games_file = "games.csv"
    output_file = "output.csv"

    process_tournament(players_file, games_file, output_file)
