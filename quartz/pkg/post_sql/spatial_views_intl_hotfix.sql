-- Hotfix for spatial views to support internationalisation. This is only required for 
-- Arches versions <7.6 as this has been fixed in 7.6.

-- #########################################################################################
-- # NOTE: This hotfix only supports the 'en' language. If you need to support another
-- #       language, you will need to modify the functions below to support the desired 
-- #       language.
-- #########################################################################################

-- Adds a language parameter to the __arches_get_resourceinstance_label function
DROP FUNCTION IF EXISTS public.__arches_get_resourceinstance_label(jsonb, text);

CREATE OR REPLACE FUNCTION public.__arches_get_resourceinstance_label(
	resourceinstance_value jsonb,
	label_type text DEFAULT 'name'::text,
	lang text DEFAULT 'en') -- << change this to the desired language code
    RETURNS text
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE PARALLEL UNSAFE
AS $BODY$
                declare
                    return_label                 text := '';
                    target_resourceinstanceid     uuid;
                begin

                    if resourceinstance_value is null or resourceinstance_value::text = 'null' then
                        return return_label;
                    end if;
                    
                    target_resourceinstanceid := ((resourceinstance_value -> 0) ->> 'resourceId')::uuid;
                    if target_resourceinstanceid is null then
                        target_resourceinstanceid := (resourceinstance_value ->> 'resourceId')::uuid;
                    end if;
                    if target_resourceinstanceid is null then
                        return return_label;
                    end if;
                    
                    select r.descriptors -> lang ->> 'name'
					into return_label
					from resource_instances r
                    where resourceinstanceid = target_resourceinstanceid;

                    if return_label = '' then
                        return 'Undefined';
                    end if;
                    return return_label;
                end;
                
$BODY$;


-- Adds a language parameter to the __arches_get_resourceinstance_list_label function
DROP FUNCTION IF EXISTS public.__arches_get_resourceinstance_list_label(jsonb, text);

CREATE OR REPLACE FUNCTION public.__arches_get_resourceinstance_list_label(
	resourceinstance_value jsonb,
	label_type text DEFAULT 'name'::text,
	lang text DEFAULT 'en') -- << change this to the desired language code
    RETURNS text
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE PARALLEL UNSAFE
AS $BODY$
                declare
                    return_label     text := '';
                begin
                    if resourceinstance_value is null OR resourceinstance_value::text = 'null' then
                        return '';
                    end if;
                    
                    select string_agg(dvl.label, ', ')
                    from
                    (
                        select __arches_get_resourceinstance_label(dv.resource_instance, label_type, lang) as label
                        from (
                            select jsonb_array_elements(resourceinstance_value) as resource_instance
                        ) dv
                    ) dvl
                    into return_label;
                    
                    return return_label;

                end;
                
$BODY$;

-- Adds a language parameter to the __arches_get_concept_label function
DROP FUNCTION IF EXISTS public.__arches_get_node_display_value(jsonb, uuid);

CREATE OR REPLACE FUNCTION public.__arches_get_node_display_value(
	in_tiledata jsonb,
	in_nodeid uuid,
	lang text DEFAULT 'en') -- << change this to the desired language code
    RETURNS text
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE PARALLEL UNSAFE
AS $BODY$
                            declare
                                display_value   text := '';
                                in_node_type    text;
                                in_node_config  json;
                            begin
                                if in_nodeid is null or in_nodeid is null then
                                    return '<invalid_nodeid>';
                                end if;

                                if in_tiledata is null then
                                    return '';
                                end if;

                                select n.datatype, n.config
                                into in_node_type, in_node_config
                                from nodes n where nodeid = in_nodeid::uuid;

                                if in_node_type = 'semantic' then
                                    return '<semantic>';
                                end if;

                                if in_node_type is null then
                                    return '';
                                end if;

                                case in_node_type
									when 'string' then
                                        display_value := ((in_tiledata -> in_nodeid::text) -> lang) ->> 'value';
                                    when 'concept' then
                                        display_value := __arches_get_concept_label((in_tiledata ->> in_nodeid::text)::uuid);
                                    when 'concept-list' then
                                        display_value := __arches_get_concept_list_label(in_tiledata -> in_nodeid::text);
                                    when 'edtf' then
                                        display_value := (in_tiledata ->> in_nodeid::text);
                                    when 'file-list' then
                                        select string_agg(f.url,' | ')
                                          from (select (jsonb_array_elements(in_tiledata -> in_nodeid::text) -> 'name')::text as url) f
                                          into display_value;
                                    when 'domain-value' then
                                        display_value := __arches_get_domain_label((in_tiledata ->> in_nodeid::text)::uuid, in_nodeid);
                                    when 'domain-value-list' then
                                        display_value := __arches_get_domain_list_label(in_tiledata -> in_nodeid, in_nodeid);
                                    when 'url' then
                                        display_value := (in_tiledata -> in_nodeid::text ->> 'url');
                                    when 'node-value' then
                                        display_value := __arches_get_nodevalue_label(in_tiledata -> in_nodeid::text, in_nodeid);
                                    when 'resource-instance' then
                                        display_value := __arches_get_resourceinstance_label(in_tiledata -> in_nodeid::text, 'name', lang);
                                    when 'resource-instance-list' then
                                        display_value := __arches_get_resourceinstance_list_label(in_tiledata -> in_nodeid::text, 'name', lang);
                                    else
                                        display_value := (in_tiledata ->> in_nodeid::text)::text;

                                    end case;

                                return display_value;
                            end;

            
$BODY$;
