class ${ModelClass}(Model):
    table_name = '${TableName}'
    PK = '${PartitionKey}'
    % if SortKey:
    SK = '${SortKey}'
    % endif

    % if UsePydantic:
    UpdateDTO = _build_pydantic_update_model(${Model})
    % else:
    % for line in DtoLines:
    ${line}
    % endfor
    % endif

    % if SortKey:
    @staticmethod
    def list(*, ${snake(PartitionKey)}: str, **kwargs) -> List[${Model}]:
        items = _query(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}}, **kwargs)
        % if UsePydantic:
        return _load_models(${Model}, items)
        % else:
        return items
        % endif
    % endif

    @staticmethod
    % if SortKey:
    def get(*, ${snake(SortKey)}: str, ${snake(PartitionKey)}: str, default: ${Model} | EllipsisType = ..., **kwargs) -> ${Model}:
        item = _get_item(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}, ${ModelClass}.SK: ${snake(SortKey)}}, default, **kwargs)
    % else:
    def get(*, ${snake(PartitionKey)}: str, default: ${Model} | EllipsisType = ..., **kwargs) -> ${Model}:
        item = _get_item(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}}, default, **kwargs)
    % endif
        if not item:
        % if SortKey:
            raise DbNotFound(f'Item was not found in {${ModelClass}.table_name} with params ${snake(PartitionKey)}={${snake(PartitionKey)}}, ${snake(SortKey)}={${snake(SortKey)}}')
        % else:
            raise DbNotFound(f'Item was not found in {${ModelClass}.table_name} with params ${snake(PartitionKey)}={${snake(PartitionKey)}}')
        % endif
        % if UsePydantic:
        return _load_model(${Model}, item)
        % else:
        return item
        % endif

    @staticmethod
    def put(${snake(Model)}: ${Model}, **kwargs) -> ${Model}:
        % if UsePydantic:
        payload = _dump_model(${snake(Model)})
        _put_item(dynamo, ${ModelClass}.table_name, payload, **kwargs)
        return _load_model(${Model}, payload)
        % else:
        _put_item(dynamo, ${ModelClass}.table_name, ${snake(Model)}, **kwargs)
        return ${snake(Model)}
        % endif

    @staticmethod
    % if SortKey:
    def update(${snake(Model)}: UpdateDTO, *, ${snake(PartitionKey)}: str, ${snake(SortKey)}: str, default: ${Model} | EllipsisType = ...) -> ${Model}:
        initial = ${ModelClass}.get(${snake(SortKey)}=${snake(SortKey)}, ${snake(PartitionKey)}=${snake(PartitionKey)}, default=default)
        % if UsePydantic:
        update_data = _dump_update_model(${snake(Model)})
        _update(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}, ${ModelClass}.SK: ${snake(SortKey)}}, without(update_data, [${ModelClass}.PK, ${ModelClass}.SK]))
        return _load_model(${Model}, {**_dump_model(initial), **update_data})
        % else:
        _update(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}, ${ModelClass}.SK: ${snake(SortKey)}}, without(${snake(Model)}, [${ModelClass}.PK, ${ModelClass}.SK]))
        return {**initial, **${snake(Model)}}
        % endif
    % else:
    def update(${snake(Model)}: UpdateDTO, *, ${snake(PartitionKey)}: str, default: ${Model} | EllipsisType = ...) -> ${Model}:
        initial = ${ModelClass}.get(${snake(PartitionKey)}=${snake(PartitionKey)}, default=default)
        % if UsePydantic:
        update_data = _dump_update_model(${snake(Model)})
        _update(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}}, without(update_data, [${ModelClass}.PK]))
        return _load_model(${Model}, {**_dump_model(initial), **update_data})
        % else:
        _update(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}}, without(${snake(Model)}, [${ModelClass}.PK]))
        return {**initial, **${snake(Model)}}
        % endif
    % endif

    @staticmethod
    % if SortKey:
    def save(updated: ${Model}, *, original: ${Model} | None = None) -> ${Model}:
        % if UsePydantic:
        updated_payload = _dump_model(updated)
        original_payload = _dump_model(original) if original else None
        _save(dynamo, ${ModelClass}.table_name, kv={${ModelClass}.PK: updated_payload[${ModelClass}.PK], ${ModelClass}.SK: updated_payload[${ModelClass}.SK]}, updated=updated_payload, original=original_payload)
        return _load_model(${Model}, updated_payload)
        % else:
        _save(dynamo, ${ModelClass}.table_name, kv={${ModelClass}.PK: updated[${ModelClass}.PK], ${ModelClass}.SK: updated[${ModelClass}.SK]}, updated=updated, original=original)
        return updated
        % endif
    % else:
    def save(updated: ${Model}, *, original: ${Model} | None = None) -> ${Model}:
        % if UsePydantic:
        updated_payload = _dump_model(updated)
        original_payload = _dump_model(original) if original else None
        _save(dynamo, ${ModelClass}.table_name, kv={${ModelClass}.PK: updated_payload[${ModelClass}.PK]}, updated=updated_payload, original=original_payload)
        return _load_model(${Model}, updated_payload)
        % else:
        _save(dynamo, ${ModelClass}.table_name, kv={${ModelClass}.PK: updated[${ModelClass}.PK]}, updated=updated, original=original)
        return updated
        % endif
    % endif

    @staticmethod
    % if SortKey:
    def delete(*, ${snake(SortKey)}: str, ${snake(PartitionKey)}: str, **kwargs):
        _delete(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}, ${ModelClass}.SK: ${snake(SortKey)}}, **kwargs)
    % else:
    def delete(*, ${snake(PartitionKey)}: str, **kwargs):
        _delete(dynamo, ${ModelClass}.table_name, {${ModelClass}.PK: ${snake(PartitionKey)}}, **kwargs)
    % endif

    @staticmethod
    def scan(**kwargs) -> List[${Model}]:
        items = _scan(dynamo, ${ModelClass}.table_name, **kwargs)
        % if UsePydantic:
        return _load_models(${Model}, items)
        % else:
        return items
        % endif

    % for index in Indexes:
    class ${pascal(index['name'])}:
        PK = '${index['PartitionKey']}'
        % if index['SortKey']:
        SK = '${index['SortKey']}'
        % endif
        
        @staticmethod
        def list(*, ${snake(index['PartitionKey'])}: str, limit: int | None = None, direction: Literal['ASC', 'DESC'] = 'ASC') -> List[${Model}]:
            items = _query(dynamo, ${ModelClass}.table_name, {${ModelClass}.${pascal(index['name'])}.PK: ${snake(index['PartitionKey'])}}, index='${index['name']}', limit=limit, direction=direction)
            % if UsePydantic:
            return _load_models(${Model}, items)
            % else:
            return items
            % endif

        % if index['SortKey']:
        @staticmethod
        def get(*, ${snake(index['PartitionKey'])}: str, ${snake(index['SortKey'])}: str) -> ${Model}:
            items = _query(dynamo, ${ModelClass}.table_name, {${ModelClass}.${pascal(index['name'])}.PK: ${snake(index['PartitionKey'])}, ${ModelClass}.${pascal(index['name'])}.SK: ${snake(index['SortKey'])}}, index='${index['name']}')
            if not items:
                raise DbNotFound(f'Item was not found in {${ModelClass}.table_name} with params ${snake(index['PartitionKey'])}={${snake(index['PartitionKey'])}}, ${snake(index['SortKey'])}={${snake(index['SortKey'])}}')

            % if UsePydantic:
            return _load_model(${Model}, items[0])
            % else:
            return items[0]
            % endif
        % endif
    % endfor
    % for vindex in VectorIndexes:
    class ${pascal(vindex['name'])}:
        @staticmethod
        def search(
            *,
            vector,
            % if vindex['hash']:
            ${snake(vindex['hash'])}: ${vindex['hash_type']},
            % endif
            top_k: int = 10,
            % for f in vindex['filters']:
            ${snake(f['attr'])}: ${f['type']} | None = None,
            % endfor
            condition_expression: str | None = None,
            expression_values: dict | None = None,
            expression_names: dict | None = None,
            projection: list[str] | None = None,
            return_consumed_capacity: str | None = None,
        ) -> SearchResults[${Model}]:
            % if vindex['hash']:
            _pv_hash_conditions = {'${vindex['hash']}': ${snake(vindex['hash'])}}
            % else:
            _pv_hash_conditions = {}
            % endif
            _pv_filter_conditions = {
            % for f in vindex['filters']:
                '${f['attr']}': ${snake(f['attr'])},
            % endfor
            }
            _pv_filter_conditions = {k: v for k, v in _pv_filter_conditions.items() if v is not None}
            _pv_results = _search_vectors(
                dynamo,
                ${ModelClass}.table_name,
                '${vindex['name']}',
                vector=vector,
                top_k=top_k,
                dimensions=${vindex['dimensions']},
                hash_conditions=_pv_hash_conditions,
                filter_conditions=_pv_filter_conditions,
                condition_expression=condition_expression,
                expression_values=expression_values,
                expression_names=expression_names,
                projection=projection,
                return_consumed_capacity=return_consumed_capacity,
            )
            % if UsePydantic:
            return SearchResults(hits=[VectorSearchResult(item=_load_model(${Model}, _pv_hit.item), score=_pv_hit.score) for _pv_hit in _pv_results.hits], consumed_capacity=_pv_results.consumed_capacity)
            % else:
            return _pv_results
            % endif
    % endfor