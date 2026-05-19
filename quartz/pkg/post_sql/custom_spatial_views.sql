-- Zone 54S (West QLD): EPSG:32754
-- Zone 55S (Central QLD): EPSG:32755
-- Zone 56S (East QLD): EPSG:32756
DROP VIEW IF EXISTS public.heritage_register_points;
CREATE OR REPLACE VIEW public.heritage_register_points AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number,
        att.monument_name,
        att.designation_or_protection_type,
        att.designation_start_date,
        att.feature_shape,
        att.coordinate_system_value,
        att.spatial_accuracy_qualifier,
        att.capture_scale,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(geo.geom, 32755)) AS easting,
        ST_Y(ST_Transform(geo.geom, 32755)) AS northing,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_heritage_item att ON geo.resourceinstanceid::text = att.resourceinstanceid
    WHERE geo.nodeid = '87d3d7dc-f44f-11eb-bee9-a87eeabdefba'::uuid
    AND ST_GeometryType(geo.geom) = 'ST_Point';

DROP VIEW IF EXISTS public.heritage_register_boundaries;
CREATE OR REPLACE VIEW public.heritage_register_boundaries AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number,
        att.monument_name,
        att.designation_or_protection_type,
        att.designation_start_date,
        att.feature_shape,
        att.coordinate_system_value,
        att.spatial_accuracy_qualifier,
        att.capture_scale,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        ST_Area(ST_Transform(geo.geom, 4326)::geography) AS area,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_heritage_item att ON geo.resourceinstanceid::text = att.resourceinstanceid
    WHERE geo.nodeid = '87d3d7dc-f44f-11eb-bee9-a87eeabdefba'::uuid
    AND ST_GeometryType(geo.geom) = 'ST_Polygon';

DROP VIEW IF EXISTS public.reported_places;
CREATE OR REPLACE VIEW public.reported_places AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.primary_reference_number,
        att.monument_name,
        att.designation_or_protection_type,
        att.designation_start_date,
        att.feature_shape,
        att.coordinate_system_value,
        att.spatial_accuracy_qualifier,
        att.capture_scale,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_heritage_item att ON geo.resourceinstanceid::text = att.resourceinstanceid
    WHERE geo.nodeid = '87d3d7dc-f44f-11eb-bee9-a87eeabdefba'::uuid
    AND att.designation_or_protection_type <> ''
    AND att.designation_or_protection_type IS NOT NULL;

DROP VIEW IF EXISTS public.artefact;
CREATE OR REPLACE VIEW public.artefact AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.date_of_assessment_start,
        att.artefact_name,
        att.validation,
        att.primary_reference_number,
        att.monument_area_or_artefact,
        att.feature_shape,
        att.coordinate_system_value,
        att.spatial_accuracy_qualifier,
        att.spatial_metadata_notes,
        att.capture_scale,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_artefact att ON geo.resourceinstanceid::text = att.resourceinstanceid
    WHERE geo.nodeid = 'f7ccc8b9-f447-11eb-9cb1-a87eeabdefba'::uuid;

DROP VIEW IF EXISTS public.historic_aircraft;
CREATE OR REPLACE VIEW public.historic_aircraft AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.designation_name,
        att.name,
        att.external_cross_reference,
        att.url,
        att.primary_reference_number,
        att.feature_shape,
        att.location_description,
        att.coordinate_system_value,
        att.spatial_accuracy_qualifier,
        att.named_location,
        att.capture_scale,
        att.status,
        att.associated_monument_area_or_artefact,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_historic_aircraft att ON geo.resourceinstanceid::text = att.resourceinstanceid
    WHERE geo.nodeid = '9766b0d4-f450-11eb-83b6-a87eeabdefba'::uuid;

DROP VIEW IF EXISTS public.maritime_vessel;
CREATE OR REPLACE VIEW public.maritime_vessel AS
    SELECT geo.id AS gid,
        geo.tileid::text,
        geo.nodeid::text,
        att.resourceinstanceid,
        att.external_cross_reference,
        att.url,
        att.status,
        att.date_of_loss_start,
        att.designation_name,
        att.feature_shape,
        att.location_description,
        att.coordinate_system_value,
        att.spatial_accuracy_qualifier,
        att.named_location,
        att.capture_scale,
        att.monument_area_or_artefact,
        att.name,
        att.primary_reference_number,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 4326)) AS longitude, 
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geo.geom), 32755)) AS easting,
        ST_Y(ST_Transform(ST_Centroid(geo.geom), 32755)) AS northing,
        geo.geom
    FROM geojson_geometries geo
        JOIN sp_attr_maritime_vessel att ON geo.resourceinstanceid::text = att.resourceinstanceid
    WHERE geo.nodeid = '9f07fa25-f457-11eb-98c7-a87eeabdefba'::uuid;
