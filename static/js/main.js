$(function () {
    $('#table').bootstrapTable({
        url: '/images/',
        pagination: true,
        sidePagination: 'server',
        pageList: [10, 25, 50, 100],
        sortName: 'date_obs',
        sortOrder: 'desc',
        showRefresh: true,
        iconsPrefix: 'fas',
        showColumns: true,
        queryParams: queryParams,
        toolbar: '#toolbar',
        columns: [{
            checkbox: true
        }, {
            field: 'name',
            title: 'Name',
            sortable: true
        }, {
            field: 'date_obs',
            title: 'Time',
            sortable: true,
        }, {
            field: 'target',
            title: 'Target',
            sortable: true,
        }, {
            field: 'image_type',
            title: 'Type',
            sortable: true,
        }, {
            field: 'exp_time',
            title: 'ExpTime',
            sortable: true
        }, {
            field: 'rlevel',
            title: 'R.level',
            sortable: true
        }],
    });

    function queryParams(params) {
        params.IMAGE_TYPE = $("#obstype").val();
        return params;
    }

    $.getJSON('/options/', function (data) {
        console.log(data);
        let options = $("#obstype");
        options.change(function() {
           $('#table').bootstrapTable('refresh');
        });
        options.append($("<option />").val('ALL').text('ALL'));
        $.each(data.image_types, function (item) {
            let t = data.image_types[item];
            options.append($("<option />").val(t).text(t));
        });
    });
});
