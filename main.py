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
            try:
                parts = line.strip().split("\t")
                parts = list(map(str.strip, parts))
                _id, name, rating, rd, vol = parts
                player_stats[_id] = (
                    name,
                    Rating(
                        mu=int(rating),
                        phi=int(rd),
                        sigma=float(vol),
                    ),
                )
            except ValueError:
                raise ValueError(
                    f"Player data input not correct. Please check that {filename}: \
                        \n- has no blank lines \
                        \n- is tab delimited \
                        \n- has columns named ID  Name    Rating  RD  RV \
                        \nIncorrect Line was: {line}"
                ) from None
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

        if not reader.fieldnames:
            raise ValueError(f"CSV file '{filename}' has no header row")

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
            try:
                cleaned_row = {
                    k.strip(): v.strip() for k, v in row.items() if k and k.strip()
                }
                cleaned_row["Rating"] = int(cleaned_row["Rating"])
                cleaned_row["Number"] = i + 1
                results.append(cleaned_row)
            except ValueError:
                raise ValueError(
                    f"Tournament data input not correct. Please check that {filename}: \
                        \n- has no blank lines \
                        \n- is tab delimited \
                        \n- has columns named ID  Name    Rnd1  Rnd 2  etc \
                        \nIncorrect Line was: {row}"
                ) from None

    return results, round_columns


def parse_round_result(result: str) -> Tuple[str, int]:
    if result == "-H-" or result == "-U-" or result == "-B-":
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
    player_round_diffs: Dict,
    round_column: str,
):
    seen_players = set()
    for player in player_results:
        result = player[round_column]
        p1_id = player["ID"]
        if p1_id in seen_players:
            continue
        seen_players.add(p1_id)
        result_type, opponent_number = parse_round_result(result)
        if result_type != "X":  # Ignore byes and unplayed games
            p1_id = player["ID"]
            p1_data = player_stats.get(p1_id)
            if p1_data is None:
                raise Exception(f"Error: Player {p1_id} not found in player stats.")
            p1_name, p1_rating = p1_data

            p2_id = player_lookup[opponent_number]
            seen_players.add(p2_id)
            p2_data = player_stats.get(p2_id)
            if p2_data is None:
                raise Exception(f"Error: Player {p2_id} not found in player stats.")
            p2_name, p2_rating = p2_data

            p1_rating_updated, p2_rating_updated = update(
                p1_rating, p2_rating, result_type
            )
            p1_round_diff = p1_rating_updated.mu - p1_rating.mu
            p2_round_diff = p2_rating_updated.mu - p2_rating.mu
            player_round_diffs[p1_id][round_column] = p1_round_diff
            player_round_diffs[p2_id][round_column] = p2_round_diff

            player_stats[p1_id] = (p1_name, p1_rating_updated)
            player_stats[p2_id] = (p2_name, p2_rating_updated)


def save_player_stats(
    initial_player_ratings: Dict[int, int],
    results: Dict,
    player_round_diffs: Dict,
    all_players_output_file: str,
    changed_players_output_file: str,
):
    try:
        with open(all_players_output_file, "w", newline="") as file:
            writer = csv.writer(file, dialect="custom")
            writer.writerow(["ID", "Name", "Rating", "RD", "RV"])
            for _id, (name, rating) in results.items():
                writer.writerow(
                    [
                        _id,
                        name,
                        round(rating.mu),
                        round(rating.phi),
                        round(rating.sigma, 8),
                    ]
                )
        print(
            f"The full set of new player ratings have been written to {all_players_output_file}"
        )

        with open(changed_players_output_file, "w", newline="") as file:
            writer = csv.writer(file, dialect="custom")

            # Header row consists of fixed fields and incremental gain fields
            columns = ["ID", "Name", "Rating", "RD", "RV"]
            columns += list(player_round_diffs[next(iter(player_round_diffs))].keys())
            columns.append("overall gain")
            writer.writerow(columns)

            for _id, rating in initial_player_ratings.items():
                player_diff = player_round_diffs[_id]
                row = []
                name, rating = results[_id]

                row.append(_id)
                row.append(name)
                row.append(round(rating.mu))
                row.append(round(rating.phi))
                row.append(round(rating.sigma, 8))

                for _, value in player_diff.items():
                    row.append(round(value))

                row.append(round(rating.mu) - initial_player_ratings[_id])
                writer.writerow(row)
        print(
            f"Updated player ratings have been written to {changed_players_output_file}"
        )
    except IOError as e:
        print(f"Error writing to output file: {e}")


def process_tournament(
    players_file: str,
    games_file: str,
    all_players_output_file: str,
    changed_players_output_file: str,
):
    player_stats = load_player_stats(players_file)
    player_results, round_columns = load_tournament_results(games_file)
    player_lookup = {player["Number"]: player["ID"] for player in player_results}
    initial_player_ratings = {
        player["ID"]: player["Rating"] for player in player_results
    }
    player_round_diffs = {
        player["ID"]: {rc: 0 for rc in round_columns} for player in player_results
    }

    for round_column in round_columns:
        print("Processing round:", round_column)
        process_round(
            player_results,
            player_stats,
            player_lookup,
            player_round_diffs,
            round_column,
        )

    save_player_stats(
        initial_player_ratings,
        player_stats,
        player_round_diffs,
        all_players_output_file,
        changed_players_output_file,
    )


if __name__ == "__main__":
    glicko2 = Glicko2(tau=0.5)

    players_file = "players.csv"
    games_file = "tournament.csv"
    all_players_output_file = "output.csv"
    changed_players_output_file = "changed_players.csv"

    process_tournament(
        players_file, games_file, all_players_output_file, changed_players_output_file
    )
