-- Zone 54S (West QLD): EPSG:32754
-- Zone 55S (Central QLD): EPSG:32755
-- Zone 56S (East QLD): EPSG:32756
DROP VIEW IF EXISTS public.heritage_register_points;
CREATE OR REPLACE VIEW public.heritage_register_points AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number AS place_id,
        att.monument_name AS place_name,
        att.spatial_accuracy_qualifier AS location_accuracy,
        att.capture_scale AS location_source,
        att.designation_start_date AS entry_date,
        att.feature_shape AS geometry_type,
        att.coordinate_system_value AS coordinate_system,
        ST_X(ST_Transform(geo.geom, 4326)) AS longitude, 
        ST_Y(ST_Transform(geo.geom, 4326)) AS latitude,
        ST_X(ST_Transform(geo.geom, 32755)) AS easting,
        ST_Y(ST_Transform(geo.geom, 32755)) AS northing,
        att.designation_or_protection_type AS place_status,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_heritage_item att ON geo.resourceinstanceid::text = att.resourceinstanceid
        JOIN resource_instances res ON geo.resourceinstanceid = res.resourceinstanceid
    WHERE geo.nodeid = '87d3d7dc-f44f-11eb-bee9-a87eeabdefba'::uuid
        AND res.resource_instance_lifecycle_state_id = '9375c9a7-dad2-4f14-a5c1-d7e329fdde4f'
        AND ST_GeometryType(geo.geom) = 'ST_Point';

DROP VIEW IF EXISTS public.heritage_register_boundaries;
CREATE OR REPLACE VIEW public.heritage_register_boundaries AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number AS place_id,
        att.monument_name AS place_name,
        att.spatial_accuracy_qualifier AS location_accuracy,
        att.capture_scale AS location_source,
        att.designation_start_date AS entry_date,
        att.feature_shape AS geometry_type,
        att.coordinate_system_value AS coordinate_system,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        att.designation_or_protection_type AS place_status,
        ST_Area(ST_Transform(geo.geom, 4326)::geography) AS area_sqm,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_heritage_item att ON geo.resourceinstanceid::text = att.resourceinstanceid
        JOIN resource_instances res ON geo.resourceinstanceid = res.resourceinstanceid
    WHERE geo.nodeid = '87d3d7dc-f44f-11eb-bee9-a87eeabdefba'::uuid
        AND res.resource_instance_lifecycle_state_id = '9375c9a7-dad2-4f14-a5c1-d7e329fdde4f'
        AND ST_GeometryType(geo.geom) = 'ST_Polygon';

DROP VIEW IF EXISTS public.reported_places;
CREATE OR REPLACE VIEW public.reported_places AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number AS place_id,
        att.monument_name AS place_name,
        att.spatial_accuracy_qualifier AS location_accuracy,
        att.capture_scale AS location_source,
        att.feature_shape AS geometry_type,
        att.coordinate_system_value AS coordinate_system,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        att.designation_or_protection_type AS place_status,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_heritage_item att ON geo.resourceinstanceid::text = att.resourceinstanceid
        JOIN resource_instances res ON geo.resourceinstanceid = res.resourceinstanceid
    WHERE geo.nodeid = '87d3d7dc-f44f-11eb-bee9-a87eeabdefba'::uuid
        AND res.resource_instance_lifecycle_state_id = '9375c9a7-dad2-4f14-a5c1-d7e329fdde4f'
        AND att.designation_or_protection_type <> ''
        AND att.designation_or_protection_type IS NOT NULL;

DROP VIEW IF EXISTS public.archaeological_discoveries;
CREATE OR REPLACE VIEW public.archaeological_discoveries AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number AS discovery_id,
        att.artefact_name AS discovery_name,
        att.monument_area_or_artefact AS related_heritage_item_or_discovery,
        att.date_of_assessment_start AS discovery_date,
        att.spatial_accuracy_qualifier AS location_accuracy,
        att.capture_scale AS location_source,
        att.feature_shape AS point_type,
        att.coordinate_system_value AS coordinate_system,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        att.validation AS assessment,
        att.spatial_metadata_notes AS point_comments,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_artefact att ON geo.resourceinstanceid::text = att.resourceinstanceid
        JOIN resource_instances res ON geo.resourceinstanceid = res.resourceinstanceid
    WHERE geo.nodeid = 'f7ccc8b9-f447-11eb-9cb1-a87eeabdefba'::uuid
        AND res.resource_instance_lifecycle_state_id = '9375c9a7-dad2-4f14-a5c1-d7e329fdde4f';

DROP VIEW IF EXISTS public.aircraft_wrecks;
CREATE OR REPLACE VIEW public.aircraft_wrecks AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number AS auchd_aircraft_id,
        att.external_cross_reference AS external_cross_reference,
        att.associated_monument_area_or_artefact AS related_heritage_item_or_discovery,
        att.url AS auchd_link,
        att.name AS name,
        att.designation_name AS jurisdiction,
        att.location_description AS location_description,
        att.spatial_accuracy_qualifier AS location_accuracy,
        att.capture_scale AS location_source,
        att.date_of_loss AS year_lost,
        att.feature_shape AS geometry_type,
        att.coordinate_system_value AS coordinate_system,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        att.status AS management_status,
        att.named_location AS protected_zone,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_historic_aircraft att ON geo.resourceinstanceid::text = att.resourceinstanceid
        JOIN resource_instances res ON geo.resourceinstanceid = res.resourceinstanceid
    WHERE geo.nodeid = '9766b0d4-f450-11eb-83b6-a87eeabdefba'::uuid
        AND res.resource_instance_lifecycle_state_id = '9375c9a7-dad2-4f14-a5c1-d7e329fdde4f';

DROP VIEW IF EXISTS public.shipwrecks;
CREATE OR REPLACE VIEW public.shipwrecks AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number AS auchd_id,
        att.external_cross_reference AS external_cross_reference,
        att.monument_area_or_artefact AS related_heritage_item_or_discovery,
        att.url AS auchd_link,
        att.name AS vessel_name,
        att.designation_name AS jurisdiction,
        att.location_description AS location_description,
        att.spatial_accuracy_qualifier AS location_accuracy,
        att.capture_scale AS location_source,
        att.date_of_loss_start AS year_lost,
        att.feature_shape AS geometry_type,
        att.coordinate_system_value AS coordinate_system,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        att.status AS management_status,
        att.named_location AS protected_zone,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_maritime_vessel att ON geo.resourceinstanceid::text = att.resourceinstanceid
        JOIN resource_instances res ON geo.resourceinstanceid = res.resourceinstanceid
    WHERE geo.nodeid = '9f07fa25-f457-11eb-98c7-a87eeabdefba'::uuid
        AND res.resource_instance_lifecycle_state_id = '9375c9a7-dad2-4f14-a5c1-d7e329fdde4f';
