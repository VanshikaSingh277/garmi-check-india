"""Features and physical direction constraints shared by train_model_a_monotone.py and build_city_hotspots.py.
-1: more of it can never make a place hotter; +1: more of it can never make a place cooler; unlisted: left free."""
FEATS = ["ndvi", "ndbi", "mndwi", "albedo", "f_tree", "f_lowveg", "f_crop", "f_built", "f_bare", "f_water", "elevation", "dist_water"]
SIGN = {"ndvi": -1, "mndwi": -1, "f_tree": -1, "f_water": -1, "ndbi": 1, "f_built": 1, "dist_water": 1}
