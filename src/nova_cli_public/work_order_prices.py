"""Work-order estimates are not submitted CMR quotes."""


def without_estimates(value):
    """Keep workflow details; quote tools alone supply submitted quote amounts."""
    if isinstance(value, dict):
        return {key: without_estimates(item) for key, item in value.items()
                if key not in {'estimated_price', 'final_price', 'estimated_cost',
                               'fmc_capped_at', 'total_amount', 'planning_estimate', 'repair_value_cents',
                               'estimate_min_cents', 'estimate_max_cents'}}
    if isinstance(value, list):
        return [without_estimates(item) for item in value]
    return value
