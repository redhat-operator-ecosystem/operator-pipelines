#!/bin/bash

YAML_FILE="ci.yaml"
OPERATOR_NAME=$(basename $(pwd))
TOPDIR=$(dirname $( dirname  $(pwd)  ) )

# Extract mappings using yq with structured formatting
mappings=$("$TOPDIR"/bin/yq eval -o=json '.fbc.catalog_mapping[]' "$YAML_FILE" | jq -c '.')

# Iterate over mappings
echo "$mappings" | while IFS= read -r mapping; do
    template_name=$(echo "$mapping" | jq -r '.template_name')
    type=$(echo "$mapping" | jq -r '.type')
    catalog_names=$(echo "$mapping" | jq -r '.catalog_names[]')

    echo "- Processing template: $template_name (Type: $type)"

    # Select command based on type
    if [[ "$type" == "olm.template.basic" ]]; then
        output=$("$TOPDIR"/bin/opm alpha render-template basic -o yaml catalog-templates/"$template_name")
    elif [[ "$type" == "olm.semver" ]]; then
        output=$("$TOPDIR"/bin/opm alpha render-template semver -o yaml catalog-templates/"$template_name")
    else
        echo "Unknown type: $type"
        exit 1
    fi

    # Check if command succeeded
    if [[ $? -ne 0 ]]; then
        echo "Error processing $template_name"
        exit 1
    fi

    # Copy output to each catalog directory
    for catalog in $catalog_names; do
        catalog_path="$TOPDIR/catalogs/$catalog/$OPERATOR_NAME"
        mkdir -p "$catalog_path"
        echo "$output" > "$catalog_path/catalog.yaml"
        echo " ✅ Template rendered to $catalog_path/catalog.yaml"
    done
done
