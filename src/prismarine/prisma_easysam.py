def build_dynamo_tables(prefix, cluster):
    "Returns: (Full Table Name with Prefix, EasySAM Table Definition)"

    result = {}

    for data in cluster.models:
        table_name = data['table']
        short_name = table_name.replace(prefix, '')

        main = data['main']

        attributes = {}
        indices = []

        if 'PK' not in main or not main['PK']:
            raise UserWarning(f'PK is required for table {table_name}')

        attributes[main['PK']] = {'hash': True}

        if 'SK' in main and main['SK']:
            attributes[main['SK']] = {'range': True}

        for index_name, index in data['indexes'].items():
            sam_index = {'name': index_name}
            index_attributes = []

            if 'PK' not in index or not index['PK']:
                raise UserWarning(f'PK is required for index {index} in table {table_name}')

            index_attributes.append({'name': index['PK'], 'hash': True})

            if index['PK'] not in attributes:
                attributes[index['PK']] = {}

            if 'SK' in index and index['SK']:
                if index['SK'] not in attributes:
                    attributes[index['SK']] = {}

                index_attributes.append({'name': index['SK'], 'range': True})

            sam_index['attributes'] = index_attributes
            indices.append(sam_index)

        # Build vector index metadata. Note (Critique E5): vector attribute/hash/filters are
        # deliberately NOT registered into the `attributes` (AttributeDefinitions) map below —
        # CloudFormation only permits attributes that serve as table or GSI/LSI key schema there,
        # so arbitrary filter attributes would break deployment. All vector metadata stays
        # confined to the `vectorindices` block.
        #
        # Billing mode (Open Question Q1): vector indexes require the table to be on-demand
        # (PAY_PER_REQUEST). The current model dict carries no billing-mode field (see
        # runtime/cluster.py), so there is nothing to assert against here; enforcement is
        # deferred to the EasySAM CloudFormation side (spec "Out of Scope") unless/until a
        # billing field is introduced on the model. We emit the block without raising.
        vector_indices = []
        for name, vindex in data.get('vector_indexes', {}).items():
            sam_vector_index = {
                'name': name,
                'attribute': vindex['attribute'],
                'dimensions': vindex['dimensions'],
                'distance': vindex['distance'],
            }

            if vindex['hash']:
                sam_vector_index['hash'] = vindex['hash']

            if vindex['filters']:
                sam_vector_index['filters'] = vindex['filters']

            vector_indices.append(sam_vector_index)

        def named_dict_to_item(name, data):
            result = {'name': name}
            result.update(data)
            return result

        result[short_name] = {
            'attributes': list(named_dict_to_item(k, v) for k, v in attributes.items()),
        }

        if indices:
            result[short_name]['indices'] = indices

        if vector_indices:
            result[short_name]['vectorindices'] = vector_indices

        # Add trigger if present in model
        if 'trigger' in data:
            result[short_name]['trigger'] = data['trigger']

        # Add TTL if present in model
        if 'ttl' in data:
            result[short_name]['ttl'] = data['ttl']

    return result
