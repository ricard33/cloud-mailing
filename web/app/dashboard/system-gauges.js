(function () {
    "use strict";

    angular.module('cm.dashboard')
        .component('systemGauges', {
            templateUrl: 'dashboard/system-gauges.html',
            controller: DashboardGraphics
        });

    function DashboardGraphics($scope, $log, $timeout, gettextCatalog, api, $filter, $q) {
        var vm = this;
        var cpu_timer = undefined;
        var disk_timer = undefined;
        vm.cpuData = [];
        vm.memoryData = [];
        vm.diskData = [];


        update_realtime_graphics();
        update_disk_graphics();

        $scope.$on('$destroy', function () {
            if (cpu_timer != undefined)
                $timeout.cancel(cpu_timer);
            if (disk_timer != undefined)
                $timeout.cancel(disk_timer);
        });

        var makeOptions = function (title) {
            return {
                chart: {
                    type: 'pieChart',
                    height: 150,
                    donut: true,
                    x: function (d) {
                        return d.key;
                    },
                    y: function (d) {
                        return d.y;
                    },
                    showLabels: true,
                    labelsOutside: true,
                    tooltip: {
                        enabled: true
                    },
                    transitionDuration: 500,
                    showLegend: false,
                    title: title
                }
            };
        };

        vm.cpuOptions = makeOptions("CPU");
        //vm.cpuOptions.chart.labelType = "percent";
        //vm.cpuOptions.chart.color = d3.scale.category10().range();
        vm.cpuOptions.chart.color = ['#ff7f0e', '#ae2323', '#23ae89'];
        vm.cpuOptions.chart.tooltip.valueFormatter = function (value) {
            return '<p>' + value.toFixed(1) + '%</p>';
        };

        vm.memoryOptions = makeOptions("Memory");
        vm.memoryOptions.chart.color = ['#ae2323', '#23ae89'];
        vm.memoryOptions.chart.tooltip.valueFormatter = function (value) {
            return '<p>' + $filter('number')(value / (1024 * 1024), 1) + ' Mb</p>';
        };
        vm.diskOptions = makeOptions("Disk");
        vm.diskOptions.chart.color = ['#ae2323', '#23ae89'];
        vm.diskOptions.chart.tooltip.valueFormatter = function (value) {
            return '<p>' + $filter('number')(value / (1024 * 1024 * 1024), 1) + ' Gb</p>';
        };


        // --------

        function update_realtime_graphics() {
            $q.all([
                api.cpu.get().$promise.then(function (cpu) {
                    //console.debug(cpu);
                    while (vm.cpuData.length) {
                        vm.cpuData.pop();
                    }
                    vm.cpuData.push({key: "system", y: cpu.system});
                    vm.cpuData.push({key: "user", y: cpu.user});
                    vm.cpuData.push({key: "idle", y: cpu.idle});
                }),

                api.memory.get().$promise.then(function (memory) {
                    //console.debug(memory);
                    while (vm.memoryData.length) {
                        vm.memoryData.pop();
                    }
                    vm.memoryData.push({key: "used", y: memory.total - memory.available});
                    vm.memoryData.push({key: "available", y: memory.available});
                })
            ]).then(function () {
                cpu_timer = $timeout(update_realtime_graphics, 5000);
            });
        }

        function update_disk_graphics() {
            $q.all([
                api.disk.get().$promise.then(function (disk) {
                    //console.debug(disk);
                    while (vm.diskData.length) {
                        vm.diskData.pop();
                    }
                    vm.diskData.push({key: "used", y: disk.used});
                    vm.diskData.push({key: "free", y: disk.free});
                })
            ]).then(function () {
                disk_timer = $timeout(update_disk_graphics, 600000);
            });


        }
    }

}());
