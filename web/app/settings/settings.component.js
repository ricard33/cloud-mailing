(function () {
    'use strict';


    angular.module('cm.settings')
        .component('settingsPage', settingsPageComponent())
    ;

    function settingsPageComponent(){
        return {
            templateUrl: 'settings/settings.html',
            controller: SettingsController
        };
    }

    function SettingsController(api){
        var vm = this;
        vm.cm = api.cm.get();

    }

}());
