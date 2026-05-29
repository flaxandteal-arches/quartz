import cytoscape from 'cytoscape';
import moment from 'moment';
import arches from 'arches';
import '../../../css/version-tree.scss';


const STATE_COLORS = {
    'Draft': '#ee6625',
    'Active': '#2E7D32',
    'Retired': '#616161',
};

const STATE_LABELS = {
    'Draft': 'Working Draft',
    'Active': 'Published',
    'Retired': 'Archived',
};

const NODE_SPACING_REM = 15;
const NODE_RADIUS_REM = 1.25;
const NODE_RADIUS_CURRENT_REM = 1.75;
const NODE_RADIUS_SMALL_REM = 1.0;
const PADDING_REM = 6;
const SVG_HEIGHT_REM = 15;
const TRUNK_Y_REM = 5;

function getRemSize() {
    return parseFloat(getComputedStyle(document.documentElement).fontSize);
}

function renderVersionTree(containerSelector, versions) {
    const container = document.querySelector(containerSelector);
    if (!container || !versions || versions.length === 0) {
        return;
    }

    const scrollContainer = container.parentElement;
    const availableWidth = scrollContainer.offsetWidth;

    const sorted = versions.slice().sort(function(a, b) {
        if (a.lifecycle_state === 'Draft' && b.lifecycle_state !== 'Draft') return -1;
        if (b.lifecycle_state === 'Draft' && a.lifecycle_state !== 'Draft') return 1;
        return new Date(b.created_at) - new Date(a.created_at);
    });

    const remPx = getRemSize();
    const nodeSpacing = NODE_SPACING_REM * remPx;
    const paddingX = PADDING_REM * remPx;
    const svgHeight = SVG_HEIGHT_REM * remPx;
    const trunkY = TRUNK_Y_REM * remPx;
    let containerWidth = (sorted.length - 1) * nodeSpacing + paddingX * 2;

    if (containerWidth < paddingX * 2 + nodeSpacing) {
        containerWidth = paddingX * 2 + nodeSpacing;
    }

    
    container.style.width = containerWidth + 'px';
    container.style.height = svgHeight + 'px';
    scrollContainer.style.width = availableWidth + 'px';

    const nodes = sorted.map(function(version, index) {
        return {
            data: {
                id: version.resourceinstanceid,
                label: 'v' + version.version_label,
                stateLabel: STATE_LABELS[version.lifecycle_state] || version.lifecycle_state,
                displayName: version.display_name || '',
                date: moment(version.created_at).format('D MMM YYYY'),
                isCurrent: version.is_current,
                lifecycleState: version.lifecycle_state,
                href: arches.urls.resource_editor + version.resourceinstanceid,
            },
            position: {
                x: paddingX + index * nodeSpacing,
                y: trunkY,
            },
        };
    });

    const edges = [];
    for (let i = 1; i < sorted.length; i++) {
        edges.push({
            data: {
                id: 'edge-' + i,
                source: sorted[i - 1].resourceinstanceid,
                target: sorted[i].resourceinstanceid,
            },
        });
    }

    const nodeRadius = NODE_RADIUS_REM * remPx;
    const nodeRadiusCurrent = NODE_RADIUS_CURRENT_REM * remPx;
    const nodeRadiusSmall = NODE_RADIUS_SMALL_REM * remPx;

    const cy = cytoscape({
        container: container,
        elements: nodes.concat(edges),
        layout: { name: 'preset', fit: false },
        zoom: 1,
        pan: { x: 0, y: 0 },
        minZoom: 1,
        maxZoom: 1,
        userZoomingEnabled: false,
        userPanningEnabled: false,
        boxSelectionEnabled: false,
        autoungrabify: true,
        style: [
            {
                selector: 'node',
                style: {
                    'width': nodeRadius * 2,
                    'height': nodeRadius * 2,
                    'background-color': function(ele) {
                        return STATE_COLORS[ele.data('lifecycleState')] || '#616161';
                    },
                    'border-width': 2,
                    'border-color': '#fff',
                    'label': function(ele) {
                        const lines = [ele.data('stateLabel'), ele.data('label'), ele.data('date')];
                        if (ele.data('displayName')) {
                            lines.splice(1, 0, ele.data('displayName'));
                        }
                        return lines.join('\n');
                    },
                    'text-wrap': 'wrap',
                    'text-valign': 'bottom',
                    'text-margin-y': remPx * 0.75,
                    'font-size': remPx * 1.1,
                    'text-halign': 'center',
                    'color': function(ele) {
                        return STATE_COLORS[ele.data('lifecycleState')] || '#616161';
                    },
                    'cursor': 'pointer',
                },
            },
            {
                selector: 'node[?isCurrent]',
                style: {
                    'width': nodeRadiusCurrent * 2,
                    'height': nodeRadiusCurrent * 2,
                    'background-color': '#06aaf6',
                    'border-width': 5,
                    'border-color': '#1E88E5',
                    "color": '#1E88E5',
                },
            },
            {
                selector: 'node[lifecycleState = "Retired"]',
                style: {
                    'width': nodeRadiusSmall * 2,
                    'height': nodeRadiusSmall * 2,
                },
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#bdbdbd',
                    'curve-style': 'straight',
                    'target-arrow-shape': 'none',
                },
            },
            {
                selector: 'node.hover',
                style: {
                    'opacity': 0.75,
                    'border-color': function(ele) {
                        return ele.data('isCurrent') ? '#1565C0' : (STATE_COLORS[ele.data('lifecycleState')] || '#616161');
                    },
                    'border-width': function(ele) {
                        return ele.data('isCurrent') ? 4 : 3;
                    },
                },
            },
        ],
    });

    const currentNode = cy.nodes('[?isCurrent]').first();
    if (currentNode.length) {
        const nodeX = currentNode.position('x');
        scrollContainer.scrollLeft = Math.max(0, nodeX - scrollContainer.clientWidth / 2);
    }

    cy.on('tap', 'node', function(event) {
        const href = event.target.data('href');
        if (href) {
            window.location.href = href;
        }
    });

    cy.on('mouseover', 'node', function(event) {
        event.target.addClass('hover');
        cy.container().style.cursor = 'pointer';
    });

    cy.on('mouseout', 'node', function(event) {
        event.target.removeClass('hover');
        cy.container().style.cursor = 'default';
    });
}

function initToggle() {
    const toggle = document.getElementById('version-tree-toggle');
    const container = document.getElementById('version-tree-container');
    const chevron = document.getElementById('version-tree-chevron');

    if (!toggle || !container) {
        return;
    }

    function setExpanded(expanded) {
        container.style.display = expanded ? '' : 'none';
        toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        chevron.className = expanded ? 'fa fa-chevron-down' : 'fa fa-chevron-right';
    }

    toggle.addEventListener('click', function() {
        const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
        setExpanded(!isExpanded);
    });

    toggle.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
            setExpanded(!isExpanded);
        }
    });
}

(function init() {
    const dataElement = document.getElementById('versionTreeData');
    if (!dataElement) {
        return;
    }

    try {
        const treeData = JSON.parse(dataElement.textContent);
        renderVersionTree(
            '#version-tree-svg',
            treeData.versions
        );
        initToggle();
    } catch (error) {
        console.error('Failed to initialize version tree:', error);
    }
})();
