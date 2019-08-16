$(function () {
    $.ajaxPrefilter(function (options, originalOptions, jqXHR) {
        if (localStorage.getItem('token')) {
            jqXHR.setRequestHeader('Authorization', 'Token ' + localStorage.getItem('token'));
        }
    });

    $('#table').bootstrapTable({
        url: '/frames/',
        ajax: function ajax(params) {
            $.ajax(queryParams(params)).fail(function () {
                // show error
            });
        },
        pagination: true,
        sidePagination: 'server',
        pageList: [10, 25, 50, 100, 250, 500],
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
            field: 'OBSTYPE',
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
        }]
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
        select.change(function () {
            $('#table').bootstrapTable('refresh');
        });
        select.append($("<option />").val('ALL').text('ALL'));
        $.each(options, function (i) {
            let t = options[i];
            select.append($("<option />").val(t).text(t));
        });
    }

    function refreshTable() {
        if ($('#table').bootstrapTable('getData').length > 0) {
            $('#table').bootstrapTable('selectPage', 1);
        } else {
            $('#table').bootstrapTable('refresh');
        }
        //history.pushState({}, '', '?q=a' + buildQueryParms(rivetsBindings.params));
    }

    function login(username, password, callback) {
        $.post('/api-token-auth/', {
            'username': username,
            'password': password
        }).done(function (data) {
            localStorage.setItem('token', data.token);
            callback(true);
        }).fail(function () {
            callback(false);
        });
    }

    function logout() {
        localStorage.removeItem('token');
    }

    $('#login').click(function () {
        login($('#email').val(), $('#password').val(), function (result) {
            if (result) {
                $('#login-form').hide();
                $('#alert').alert('close');
                $('#logout').show();
                refreshTable();
            } else {
                if ($("#alert-error").find("div#alert").length == 0) {
                    $("#alert-error").append("<div class='alert alert-danger alert-dismissable' id='alert'>" +
                        "<button type='button' class='close' data-dismiss='alert' aria-hidden='true'>&times;</button> " +
                        "Login failed.</div>");
                }
            }
        });
    });

    $('#logout').click(function () {
        logout();
        $('#login-form').show();
        $('#logout').hide();
        refreshTable();
    });

    if (localStorage.getItem('token') !== null) {
        $('#login-form').hide();
        $('#logout').show();
    }

    // get options
    $.getJSON('/frames/aggregate/', function (data) {
        setOptions($('#imagetype'), data.imagetypes);
        setOptions($('#site'), data.sites);
        setOptions($('#telescope'), data.telescopes);
        setOptions($('#instrument'), data.instruments);
        setOptions($('#filter'), data.filters);
        setOptions($('#rlevel'), ['raw', 'reduced']);
    });

    function zipDownload() {
        let selections = $('#table').bootstrapTable('getSelections');

        let frames = [];
        for (let i = 0; i < selections.length; i++) {
            frames.push(selections[i].id);
        }

        $.fileDownload('/frames/zip/', {
            httpMethod: 'POST',
            data: {'frame_ids': frames, 'auth_token': localStorage.getItem('token')},
            headers: {}
        });
    }

    $('#downloadBtn').on('click', function () {
        zipDownload();
    });
});
