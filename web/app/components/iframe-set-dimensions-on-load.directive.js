(function () {
    "use strict";

    angular.module('app')
        .directive('iframeSetDimensionsOnLoad', function ($log) {
            return {
                restrict: 'A',
                link: function (scope, element, attrs) { // eslint-disable-line no-unused-vars
                    element.on('load', function () {
                        /* Set the dimensions here,
                         I think that you were trying to do something like this: */
                        var iFrameHeight = element[0].contentWindow.document.body.scrollHeight + 'px';
                        var iFrameWidth = '100%';
                        $log.debug("Height:", iFrameHeight);
                        element.css('width', iFrameWidth);
                        element.css('height', iFrameHeight);
                    });
                }
            };
        });
}());
