"""Site surfaces (driveway, patio, paths) and planting (trees, shrubs, hedges)."""

from mesh_utils import create_element


def create_site_area(element: dict, collection, material):
    return create_element(element, collection, material, "site")


def create_vegetation(element: dict, collection, material):
    obj = create_element(element, collection, material, "vegetation")
    if element.get("tags", {}).get("part") == "foliage" and element.get("mesh"):
        for polygon in obj.data.polygons:  # rounded canopies read as foliage rather than facets
            polygon.use_smooth = True
    return obj
