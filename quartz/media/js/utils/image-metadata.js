import arches from "arches";

const cache = new Map();

const fetchImageMetadata = function (fileId) {
    if (!cache.has(fileId)) {
        const url = arches.urls.url_subpath + "/image-metadata/" + fileId;
        cache.set(
            fileId,
            fetch(url, { credentials: "same-origin" })
                .then((response) => (response.ok ? response.json() : { fields: [] }))
                .catch(() => ({ fields: [] }))
        );
    }
    return cache.get(fileId);
};

export default { fetchImageMetadata };
