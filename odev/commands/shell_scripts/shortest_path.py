def shortest_path(env, model_a, model_b, n=10, display=True):
    """
    Return the n shortest paths from model_a to model_b using a BFS algorithm.
    """
    missing_models = [model for model in [model_a, model_b] if env.get(model) is None]
    if missing_models:
        raise Exception(
            f"Model(s) {', '.join(missing_models)} not found in database. Please install the module(s) that define it"
        )

    paths_to_return = []
    path_list = [[(model_a, "self")]]
    path_index = 0
    models_done = {model_a}

    if model_a == model_b:
        return path_list[0]

    while path_index < len(path_list) and len(paths_to_return) < n:
        current_path = path_list[path_index]
        last_model = current_path[-1][0]
        next_fields = last_model.fields_get()
        next_models = {env[val.get("relation")]: field for field, val in next_fields.items() if val.get("relation")}

        for next_model in next_models.keys():
            if model_b == next_model:
                paths_to_return.append(current_path + [(model_b, next_models[model_b])])

            if next_model not in models_done:
                new_path = current_path[:]
                new_path.append((next_model, next_models[next_model]))
                path_list.append(new_path)
                # To avoid backtracking
                models_done.add(next_model)

        # Continue to next path in list
        path_index += 1
    if display and paths_to_return:
        for path in paths_to_return:
            print(".".join([field for model, field in path]))
    return paths_to_return
