moment().format();

const Utils = {
    isNumeric: function isNumeric(number) {
        return !isNaN(parseFloat(number) && isFinite(number));
    },

    sexagesimalRaToDecimal: function sexagesimalRaToDecimal(ra) {
        // algorithm: ra_decimal = 15 * ( hh + mm/60 + ss/(60 * 60) )
        /*                 (    hh     ):(     mm            ):  (   ss  ) */
        var m = ra.match('^([0-9]?[0-9]):([0-5]?[0-9][.0-9]*):?([.0-9]+)?$');
        if (m) {
            var hh = parseInt(m[1], 10);
            var mm = parseFloat(m[2]);
            var ss = m[3] ? parseFloat(m[3]) : 0.0;
            if (hh >= 0 && hh <= 23 && mm >= 0 && mm < 60 && ss >= 0 && ss < 60) {
                ra = (15.0 * (hh + mm / 60.0 + ss / 3600.0)).toFixed(10);
            }
        }
        return ra;
    },

    sexagesimalDecToDecimal: function sexagesimalDecToDecimal(dec) {
        // algorithm: dec_decimal = sign * ( dd + mm/60 + ss/(60 * 60) )
        /*                  ( +/-   ) (    dd     ):(     mm            ): (   ss   ) */
        var m = dec.match('^([+-])?([0-9]?[0-9]):([0-5]?[0-9][.0-9]*):?([.0-9]+)?$');
        if (m) {
            var sign = m[1] === '-' ? -1 : 1;
            var dd = parseInt(m[2], 10);
            var mm = parseFloat(m[3]);
            var ss = m[4] ? parseFloat(m[4]) : 0.0;
            if (dd >= 0 && dd <= 90 && mm >= 0 && mm <= 59 && ss >= 0 && ss <= 59) {
                dec = (sign * (dd + mm / 60.0 + ss / 3600.0)).toFixed(10);
            }
        }
        return dec;
    }
};

function setRequestHeader(xhr) {
    if (localStorage.getItem('token')) {
        xhr.setRequestHeader('Authorization', 'Token ' + localStorage.getItem('token'));
    }
}

$(function () {
    // Animate loader off screen
    $(".loading").fadeOut("slow");

    $.ajaxPrefilter(function (options, originalOptions, jqXHR) {
        setRequestHeader(jqXHR);
    });

    $('#table').bootstrapTable({
        url: '/api/frames/',
        ajaxOptions: {
            beforeSend: function (xhr) {
                setRequestHeader(xhr);
            }
        },
        totalField: 'count',
        dataField: 'results',
        pagination: true,
        sidePagination: 'server',
        pageSize: 25,
        pageList: [10, 25, 50, 100, 250, 500],
        sortName: 'DATE_OBS',
        sortOrder: 'desc',
        showRefresh: true,
        iconsPrefix: 'fas',
        showColumns: true,
        queryParams: queryParams,
        toolbar: '#toolbar',
        detailView: true,
        showExport: true,
        clickToSelect: true,
        detailFormatter: detailFormatter,
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
            field: 'OBJECT',
            title: 'Object',
            sortable: true,
        }, {
            field: 'OBSTYPE',
            title: 'Type',
            sortable: true,
        }, {
            field: 'binning',
            title: 'Bin',
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

    $('#daterange').daterangepicker({
        'locale': {
            'format': 'YYYY-MM-DD HH:mm'
        },
        'timePicker': true,
        'timePicker24Hour': true,
        'timePickerIncrement': 10,
        'ranges': {
            'This Year': [moment.utc().startOf('year'), moment.utc().endOf('year')],
            'Last Year': [moment.utc().subtract(1, 'year').startOf('year'), moment.utc().subtract(1, 'year').endOf('year')],
            'All Time': [moment('2000-01-01'), moment.utc().endOf('day').add(1, 'days')],
            'Today': [moment.utc().startOf('day'), moment.utc().endOf('day')],
            'Yesterday': [moment.utc().startOf('day').subtract(1, 'days'), moment.utc().endOf('day').subtract(1, 'days')],
            'Last 7 Days': [moment.utc().startOf('day').subtract(6, 'days'), moment.utc().endOf('day')],
            'Last 30 Days': [moment.utc().startOf('day').subtract(29, 'days'), moment.utc().endOf('day')]
        }
    }, setDateRange);

    function setDateRange(start, end) {
        $('#date-start').html(start.format('YYYY-MM-DD HH:mm'));
        $('#date-end').html(end.format('YYYY-MM-DD HH:mm'));
        refreshTable();
    }

    setDateRange(moment.utc().startOf('year'), moment.utc().endOf('year'));

    function queryParams(params) {
        params.IMAGETYPE = $("#imagetype").val();
        params.binning = $('#binning').val();
        params.SITE = $('#site').val();
        params.TELESCOPE = $('#telescope').val();
        params.INSTRUMENT = $('#instrument').val();
        params.FILTER = $('#filter').val();
        params.RLEVEL = $('#rlevel').val();
        params.EXPTIME = $('#exptime').val();
        params.OBJECT = $('#object').val();
        params.RA = Utils.sexagesimalRaToDecimal($('#xloc').val());
        params.DEC = Utils.sexagesimalDecToDecimal($('#yloc').val());
        params.basename = $('#basename').val();
        params.start = $('#date-start').html();
        params.end = $('#date-end').html();
        return params;
    }

    function detailFormatter(index, row, $detail) {
        $.getJSON('/api/frames/' + row.id + '/related/', function (data) {
            // build HTML
            let div = $detail.html(`
              <div class="row">
                <div class="col-md-8">
                  <h4>Calibration and Catalog Frames</h4>
                  <table class="table table-sm image-data"></table>
                </div>
                <div class="col-md-4 text-center">
                  <button class="btn btn-outline-primary btn-sm btn-block">FITS headers</button>
                  <img src="/static/img/ajax-loader.gif" alt="Thumbnail" />
                </div>
              </div>
            `);

            // get table and create it
            div.find('.table').bootstrapTable({
                columns: [
                    {
                        checkbox: true
                    }, {
                        field: 'basename',
                        title: 'Name',
                        sortable: true
                    }, {
                        field: 'OBSTYPE',
                        title: 'Type',
                        sortable: true,
                    }
                ],
                data: data,
                clickToSelect: true,
                checkBoxHeader: false
            });

            // image
            div.find('img').attr('src', '/api/frames/' + row.id + '/preview/');

            // click on button
            div.find('button').click(function() {
                $.getJSON('/api/frames/' + row.id + '/headers/', function (data) {
                    // build table
                    let table = '<table class="table">';
                    for (let i = 0; i < data.results.length; i++) {
                        table += '<tr><th>' + data.results[i].key + '</th><td>' + data.results[i].value + '</td></tr>';
                    }
                    table += '</table>';

                    // show modal window
                    $('#headerModalBody').html(table);
                    $('#headerModal').modal();
                });
            });
        });
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

    $('.keyup').typeWatch({
        callback: function callback() {
            refreshTable();
        },
        wait: 500,
        highlight: true,
        captureLength: 1
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
    $.getJSON('/api/frames/aggregate/', function (data) {
        setOptions($('#imagetype'), data.imagetypes);
        setOptions($('#binning'), data.binnings);
        setOptions($('#site'), data.sites);
        setOptions($('#telescope'), data.telescopes);
        setOptions($('#instrument'), data.instruments);
        setOptions($('#filter'), data.filters);
        setOptions($('#rlevel'), ['0', '1']);
    });

    function zipDownload() {
        // loop all data tables and collect frames
        let frames = [];
        $('table.image-data').each(function() {
            // get selected frames
            let selections = $(this).bootstrapTable('getSelections');

            // add them to list
            for (let i = 0; i < selections.length; i++) {
                frames.push(selections[i].id);
            }
        });

        if (frames.length > 0) {
            $.fileDownload('/api/frames/zip/', {
                httpMethod: 'POST',
                data: {'frame_ids': frames, 'auth_token': localStorage.getItem('token')},
                headers: {}
            });
        }
    }

    $('#downloadBtn').on('click', function () {
        zipDownload();
    });

    function lookup() {
        var name = $('#location').val();
        $.getJSON('https://simbad2k.lco.global/' + name, function (data) {
            $('#xloc').val(data.ra.replace(/\ /g, ':'));
            $('#yloc').val(data.dec.replace(/\ /g, ':'));
            refreshTable();
        });
    }

    $('#lookup-btn').click(function () {
        lookup();
    });
//# sourceMappingURL=lookup.js.map
});
