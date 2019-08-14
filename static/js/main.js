$(function () {
    $('#table').bootstrapTable({
        url: '/images/',
        pagination: true,
        sidePagination: 'server',
        pageList: [10, 25, 50, 100],
        sortName: 'DATE_OBS',
        sortOrder: 'desc',
        showRefresh: true,
        iconsPrefix: 'fas',
        showColumns: true,
        queryParams: queryParams,
        toolbar: '#toolbar',
        columns: [{
            checkbox: true
        }, {
            field: 'basename',
            title: 'Name',
            sortable: true
        }, {
            field: 'DATE_OBS',
            title: 'Time',
            sortable: true,
        }, {
            field: 'TARGET',
            title: 'Target',
            sortable: true,
        }, {
            field: 'IMAGETYP',
            title: 'Type',
            sortable: true,
        }, {
            field: 'FILTER',
            title: 'Filter',
            sortable: true,
        }, {
            field: 'EXPTIME',
            title: 'ExpTime',
            sortable: true
        }, {
            field: 'RLEVEL',
            title: 'R.level',
            sortable: true
        }],
    });

    function queryParams(params) {
        params.IMAGETYPE = $("#imagetype").val();
        params.SITE = $('#site').val();
        params.TELESCOPE = $('#telescope').val();
        params.INSTRUMENT = $('#instrument').val();
        params.FILTER = $('#filter').val();
        params.RLEVEL = $('#rlevel').val();
        return params;
    }

    function setOptions(select, options) {
        select.change(function() {
           $('#table').bootstrapTable('refresh');
        });
        select.append($("<option />").val('ALL').text('ALL'));
        $.each(options, function (i) {
            let t = options[i];
            select.append($("<option />").val(t).text(t));
        });
    }

    // get options
    $.getJSON('/options/', function (data) {
        setOptions($('#imagetype'), data.imagetypes);
        setOptions($('#site'), data.sites);
        setOptions($('#telescope'), data.telescopes);
        setOptions($('#instrument'), data.instruments);
        setOptions($('#filter'), data.filters);
        setOptions($('#rlevel'), ['raw', 'reduced']);
    });
});
