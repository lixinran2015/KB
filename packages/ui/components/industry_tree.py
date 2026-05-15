from typing import Any, Dict, List, Tuple


def build_sunburst_data(industry: Dict[str, Any]) -> Tuple[List[str], List[str], List[float], List[str]]:
    """Convert industry YAML to Plotly Sunburst data.

    Returns: (labels, parents, values, colors)
    """
    labels = []
    parents = []
    values = []
    colors = []

    industry_name = industry["name"]
    labels.append(industry_name)
    parents.append("")
    values.append(100)
    colors.append("#1f77b4")  # Root color

    layer_colors = {
        "upstream": "#4a90d9",
        "midstream": "#5cb85c",
        "downstream": "#f0ad4e",
    }

    for layer_key, layer_name in [("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游")]:
        layer = industry.get(layer_key)
        if not layer:
            continue

        layer_display = layer.get("name", layer_name)
        labels.append(layer_display)
        parents.append(industry_name)
        values.append(33)
        colors.append(layer_colors.get(layer_key, "#999"))

        for segment in layer.get("segments", []):
            seg_name = segment["name"]
            labels.append(seg_name)
            parents.append(layer_display)
            # Use value_chain_pct if available, else default
            val = segment.get("value_chain_pct", 10)
            values.append(val * 100 if val < 1 else val)
            colors.append(layer_colors.get(layer_key, "#999"))

            # Handle sub_segments
            for sub in segment.get("sub_segments", []):
                sub_name = sub if isinstance(sub, str) else sub.get("name", "")
                labels.append(sub_name)
                parents.append(seg_name)
                values.append(5)
                colors.append(layer_colors.get(layer_key, "#999"))

    return labels, parents, values, colors
