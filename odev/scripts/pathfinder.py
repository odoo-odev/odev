# Find the shortest path between two models in a database using the BFS algorithm


def check_installed_models(env, models):
    """Check that the models are installed on the database."""
    missing_models = [model for model in models if model not in env]

    if missing_models:
        raise Exception(
            f"""
            Model(s) {', '.join(missing_models)} not found in database.
            Make sure all modules are installed and up-to-date.
            """
        )


def pathfinder(env, origin, destination):
    """Find the paths between two models in a database using the BFS algorithm."""
    check_installed_models(env, [origin, destination])

    all_paths = [[(origin, "self", "")]]

    if origin == destination:
        return all_paths

    complete_paths = []
    explored = {origin}
    index = 0

    while index < len(all_paths):
        current_path = all_paths[index]
        last_model = current_path[-1][0]
        next_fields = env[last_model].fields_get()
        next_models = {
            value.get("relation"): (field, value.get("type"))
            for field, value in next_fields.items()
            if "relation" in value
        }

        for next_model in next_models.keys():
            if destination == next_model:
                current_path += [(destination, *next_models[destination])]

                if complete_paths and len(current_path) > len(complete_paths[0]) + 1:
                    return complete_paths

                complete_paths.append(current_path)
                break

            if next_model not in explored:
                new_path = current_path[:]
                new_path.append((next_model, *next_models[next_model]))
                all_paths.append(new_path)
                explored.add(next_model)

        index += 1

    return complete_paths
