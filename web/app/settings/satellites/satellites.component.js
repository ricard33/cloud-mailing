(function () {
    'use strict';


    angular.module('cm.settings')
        .component('satellitesPage', {
            templateUrl: 'settings/satellites/satellites.html',
            controller: SatellitesController
        });

    function SatellitesController(api){
        var vm = this;
        vm.cm = api.cm.get();

        vm.satellites = api.satellites.get();
    }

}());
