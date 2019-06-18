(function () {
    "use strict";

    angular.module('cm.dashboard')
        .component('hourlyGraphics', {
            templateUrl: 'dashboard/hourly-graphics.html',
            controller: HourlyGraphicsController
        });

    function HourlyGraphicsController($scope, $log, $timeout, gettextCatalog, api) {
        var vm = this;
        vm.offset = 0;
        vm.slice = 24;
        var tries = {key: "Tries", values: []};
        var sent = {key: "Sent", values: []};
        var failed = {key: "Failed", values: []};
        vm.hourlyData = [
            tries,
            sent,
            failed
        ];

        var update_timer = undefined;

        update_graphics();

        $scope.$on('$destroy', function () {
            if(update_timer != undefined)
                $timeout.cancel(update_timer);
        });

        vm.hourlyOptions = {
            chart: {
                type: 'cumulativeLineChart',
                height: 220,
                margin: {
                    top: 20,
                    right: 20,
                    bottom: 60,
                    left: 65
                },
                x: function (d) {
                    return d[0];
                },
                y: function (d) {
                    return d[1];
                },
                //average: function(d) { return d.mean/100; },

                color: ['#337ab7', '#23ae89', '#ae2323'],
                transitionDuration: 300,
                useInteractiveGuideline: true,
                clipVoronoi: false,

                xAxis: {
                    axisLabel: 'Date',
                    tickFormat: function (epoch) {
                        return d3.time.format('%d/%m/%Y %H:%M')(new Date(epoch * 3600 * 1000));
                    },
                    showMaxMin: true,
                    staggerLabels: true
                },

                yAxis: {
                    axisLabel: 'Emails',
                    //tickFormat: function(d){
                    //    return d3.format(',.1%')(d);
                    //},
                    showMaxMin: true,
                    axisLabelDistance: 20
                    //domain: [0,100]
                },
                //yDomain: [0,100],
                //yScale: [0,100],
                //forceY: [100],
                rescaleY: true

            }
        };

        vm.prev = function () {
            vm.offset -= vm.slice;
            update_graphics();
        };
        vm.next = function () {
            vm.offset += vm.slice;
            vm.offset = Math.min(vm.offset, 0);
            update_graphics();
        };
        vm.set_slice = function (hours) {
            vm.slice = hours;
            update_graphics();
        };

        //    chart: {
        //        type: 'pieChart',
        //        height: 150,
        //        donut: true,
        //        x: function(d){return d.key;},
        //        y: function(d){return d.y;},
        //        showLabels: true,
        //        donutLabelsOutside: true,
        //        //tooltips: true,
        //        title: "Memory",
        //        transitionDuration: 500,
        //        showLegend: false,
        //    }
        //};

        //vm.xFunction = function () {
        //    return function (d) {
        //        return d.key;
        //    };
        //};
        //
        //vm.yFunction = function () {
        //    return function (d) {
        //        return d.y;
        //    };
        //};


        function update_graphics() {
            if(update_timer != undefined){
                $timeout.cancel(update_timer);
                update_timer = undefined;
            }
            var filters = {};
            filters.from_date = new Date();
            filters.from_date.setHours(filters.from_date.getHours() + vm.offset - vm.slice);
            if (vm.offset) {
                filters.to_date = new Date();
                filters.to_date.setHours(filters.to_date.getHours() + vm.offset);
            }
            return api.hourlyStats.query(filters).$promise.then(function (data) {
                // $log.debug(data);
                while (tries.values.length > 0) {
                    tries.values.pop();
                }
                while (sent.values.length > 0) {
                    sent.values.pop();
                }
                while (failed.values.length > 0) {
                    failed.values.pop();
                }
                for (var i = 0; i < data.items.length; i++) {
                    //if(tries.values.length > 0 && tries.values[tries.values.length - 1][0] === data.items[i].epoch_hour) {
                    //    tries.values[tries.values.length - 1][1] += data.items[i].tries;
                    //    sent.values[sent.values.length - 1][1] += data.items[i].sent;
                    //    failed.values[failed.values.length - 1][1] += data.items[i].failed;
                    //} else {
                    tries.values.push([data.items[i].epoch_hour, data.items[i].tries]);
                    sent.values.push([data.items[i].epoch_hour, data.items[i].sent]);
                    failed.values.push([data.items[i].epoch_hour, data.items[i].failed]);
                    //}
                }
                //console.debug(vm.hourlyData);
            }).then(function(){
                update_timer = $timeout(update_graphics, 30000);
            });
        }
    }

}());
